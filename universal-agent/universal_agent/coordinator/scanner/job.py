"""Job scan coordinator — domain-isolated, reuses Core event/memory infra.

Proves Universal Core handles Job domain with ZERO core changes (§64):
  - same EventEnvelope / EventBus / ObservationStore
  - same Candidate/Offer/Quote contracts
  - same registry health degradation (§53)
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from ...core.contracts import (
    Candidate,
    Offer,
    Quote,
    RawJob,
    TaskSpec,
    new_id,
)
from ...domains.jobs import entity_key, normalize_job, score_job
from ...events import EventBusProtocol, EventEnvelope, EventType
from ...memory import ObservationStore
from ...registry import SkillRegistry

log = logging.getLogger("ua.coordinator.job_scan")

JobFetcher = Callable[..., List[RawJob]]


@dataclass
class JobScanOutcome:
    trace_id: str
    task_id: str
    candidates: List[Candidate] = field(default_factory=list)
    offers: List[Offer] = field(default_factory=list)
    quotes: List[Quote] = field(default_factory=list)
    raw_jobs: List[RawJob] = field(default_factory=list)
    top3: List[RawJob] = field(default_factory=list)
    emitted_events: List[str] = field(default_factory=list)

    def summary(self) -> Dict:
        return {
            "trace_id": self.trace_id,
            "task_id": self.task_id,
            "raw_jobs": len(self.raw_jobs),
            "candidates": len(self.candidates),
            "top3": [f"{j.title}@{j.company}" for j in self.top3],
        }


class JobScanCoordinator:
    def __init__(self, *, bus: EventBusProtocol, registry: SkillRegistry,
                 observations: Optional[ObservationStore] = None,
                 fetchers: Optional[Dict[str, JobFetcher]] = None,
                 wanted_skills: Optional[List[str]] = None) -> None:
        self.bus = bus
        self.registry = registry
        self.observations = observations
        self.fetchers = fetchers or {}
        self.wanted_skills = wanted_skills or []

    async def scan(self, task: TaskSpec) -> JobScanOutcome:
        trace_id = new_id("trace")
        outcome = JobScanOutcome(trace_id=trace_id, task_id=task.id)
        await self._emit(EventType.SCAN_REQUESTED, outcome, task_id=task.id,
                         payload={"task_id": task.id, "trace_id": trace_id})

        raw_jobs: List[RawJob] = []
        # 职位关键词来自任务 search_space（如 title 关键词）
        keywords = task.search_space.extra.get("keywords", [""])
        for kw in keywords:
            for marketplace_id, fetcher in self.fetchers.items():
                try:
                    batch = await asyncio.to_thread(fetcher, kw)
                except Exception as exc:  # noqa: BLE001 — §48
                    log.warning("job source %s failed for %r: %s",
                                marketplace_id, kw, exc)
                    if self.registry.get_marketplace(marketplace_id) is not None:
                        self.registry.set_marketplace_health(marketplace_id, "DEGRADED")
                    continue
                for job in batch:
                    await self._emit(EventType.RAW_LISTING_DISCOVERED, outcome,
                                     payload={"job_id": job.job_id,
                                              "source": job.marketplace_id})
                    raw_jobs.append(job)

        seen: Dict[str, str] = {}
        for job in raw_jobs:
            cand, offer, quote, evidence = normalize_job(job, task.id, self.wanted_skills)
            key = entity_key(job)
            if key in seen:
                cand.candidate_id = seen[key]
                offer.candidate_id = cand.candidate_id
            else:
                seen[key] = cand.candidate_id
                outcome.candidates.append(cand)
                await self._emit(EventType.CANDIDATE_CREATED, outcome,
                                 payload={"candidate_id": cand.candidate_id,
                                          "entity_key": key})
            outcome.offers.append(offer)
            outcome.quotes.append(quote)
            outcome.raw_jobs.append(job)
            await self._emit(EventType.QUOTE_OBSERVED, outcome,
                             payload={"offer_id": offer.offer_id,
                                      "price": quote.price.amount})

        # 评分 + Top3（§64 Job Watch）
        if raw_jobs:
            mids = [__import__("universal_agent.domains.jobs", fromlist=["salary_midpoint"])
                    .salary_midpoint(j) for j in raw_jobs]
            mids = [m for m in mids if m > 0]
            market = sum(mids) / len(mids) if mids else 0.0
            scored = [(j, score_job(j, market, self.wanted_skills)["total"])
                      for j in raw_jobs]
            scored.sort(key=lambda x: x[1], reverse=True)
            outcome.top3 = [j for j, _ in scored[:3]]

        await self._emit(EventType.SCAN_COMPLETED, outcome,
                         payload={"jobs": len(raw_jobs)})
        return outcome

    async def _emit(self, event_type: EventType, outcome: JobScanOutcome,
                    task_id: Optional[str] = None, payload: Optional[Dict] = None) -> None:
        envelope = EventEnvelope(
            event_type=event_type,
            trace_id=outcome.trace_id,
            task_id=task_id or outcome.task_id,
            source="job_scan_coordinator",
            payload=payload or {},
        )
        outcome.emitted_events.append(event_type.value)
        await self.bus.publish(envelope)
