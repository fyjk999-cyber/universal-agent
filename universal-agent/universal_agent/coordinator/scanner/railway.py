"""Railway scan coordinator — 12306 真实数据全流程（P23 / CH7）。

Scan → Normalize → Entity(Dedup) → Score → Rank → Opportunity → Notify
- 源：`railway_12306`（12306 公开接口，无 key）
- 确定性评分（domains/railway/scoring.py，RULE-005）
- 机会判定：余票可得（有票/余票>0）+ 时刻/历时优 → OPPORTUNITY
- 通知：notifier 钩子（host send_notification，FR-031 同链）

域隔离（RULE-003/§17 独立失败）：Railway 源失败不影响其他域。
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
    RawRailway,
    TaskSpec,
    new_id,
)
from ...domains.railway import entity_key, normalize_railway, score_railway
from ...events import EventBusProtocol, EventType
from ...registry import SkillRegistry

log = logging.getLogger("ua.coordinator.railway_scan")

#: 源 callable(from_city, to_city, date) → list[RawRailway]
RailwayFetcher = Callable[..., List[RawRailway]]


@dataclass
class RailwayScanOutcome:
    trace_id: str
    task_id: str
    candidates: List[Candidate] = field(default_factory=list)
    offers: List[Offer] = field(default_factory=list)
    quotes: List[Quote] = field(default_factory=list)
    raw_railways: List[RawRailway] = field(default_factory=list)
    ranked: List[Dict] = field(default_factory=list)   # [{raw, score, components}]
    top: List[RawRailway] = field(default_factory=list)
    opportunity: Optional[Dict] = None
    notified: bool = False
    verification: Dict = field(default_factory=dict)   # FR-117：新鲜度/完整性
    emitted_events: List[str] = field(default_factory=list)


class RailwayScanCoordinator:
    def __init__(self, *, bus: EventBusProtocol, registry: SkillRegistry,
                 fetchers: Optional[Dict[str, RailwayFetcher]] = None,
                 notifier: Optional[Callable[[Dict], None]] = None,
                 top_n: int = 5) -> None:
        self.bus = bus
        self.registry = registry
        self.fetchers = fetchers or {}
        self.notifier = notifier  # FR-031：机会通知真实投递
        self.top_n = top_n

    async def scan(self, task: TaskSpec) -> RailwayScanOutcome:
        trace_id = new_id("trace")
        outcome = RailwayScanOutcome(trace_id=trace_id, task_id=task.id)
        await self._emit(EventType.SCAN_REQUESTED, outcome,
                         payload={"task_id": task.id, "trace_id": trace_id})

        space = task.search_space
        origins = space.origin or ["上海"]
        dests = space.destination or []
        date = ((space.departure or {}).get("start") or "")[:10] or ""

        raw_list: List[RawRailway] = []
        for origin in origins:
            for dest in dests:
                for marketplace_id, fetcher in self.fetchers.items():
                    try:
                        # fetcher 契约：可接受 (from, to, date) 元组 或 字典
                        batch = await asyncio.to_thread(
                            fetcher, (origin, dest, date))
                    except Exception as exc:  # noqa: BLE001 — §48 失败隔离
                        log.warning("railway source %s failed %s->%s: %s",
                                    marketplace_id, origin, dest, exc)
                        if self.registry.get_marketplace(marketplace_id) is not None:
                            self.registry.set_marketplace_health(
                                marketplace_id, "DEGRADED")
                        continue
                    for raw in batch:
                        await self._emit(EventType.RAW_LISTING_DISCOVERED, outcome,
                                         payload={"railway_id": raw.railway_id,
                                                  "source": raw.marketplace_id})
                        raw_list.append(raw)

        # ---- normalize + entity dedup（train+route+date 为候选；座别为 offer）----
        seen: Dict[str, str] = {}
        for raw in raw_list:
            cand, offer, quote, evidence = normalize_railway(raw, task.id)
            key = entity_key(raw)
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
            outcome.raw_railways.append(raw)
            await self._emit(EventType.QUOTE_OBSERVED, outcome,
                             payload={"offer_id": offer.offer_id,
                                      "price": quote.price.amount})

        # ---- score + rank（确定性，RULE-005）----
        prices = [r.price_cny for r in raw_list if r.price_cny > 0]
        market_min = min(prices) if prices else 0.0
        scored = []
        for raw in raw_list:
            comp = score_railway(raw, market_min)
            scored.append({"raw": raw, "score": comp["total"], "components": comp})
        scored.sort(key=lambda x: x["score"], reverse=True)
        outcome.ranked = scored
        outcome.top = [s["raw"] for s in scored[: self.top_n]]

        # ---- FR-117 verification（12306 为权威源；校验新鲜度 + 完整性）----
        from ...domains.railway import verify_railway
        if raw_list:
            v = verify_railway(raw_list[0], query_date=date)
            outcome.verification = v
            await self._emit(EventType.VERIFICATION_COMPLETED, outcome,
                             payload={"status": v["status"], "reasons": v["reasons"]})

        # ---- opportunity + notify（余票可得 = 机会）----
        await self._evaluate_opportunity(task, outcome)

        await self._emit(EventType.SCAN_COMPLETED, outcome,
                         payload={"railway": len(raw_list),
                                  "top": len(outcome.top)})
        return outcome

    async def _evaluate_opportunity(self, task: TaskSpec,
                                    outcome: RailwayScanOutcome) -> None:
        if not outcome.ranked:
            return
        top = outcome.ranked[0]
        raw: RawRailway = top["raw"]
        avail = str(raw.extra.get("available", "")).strip()
        available = avail not in ("", "无", "0")
        if not available:
            return
        # 机会 = 可预订 + 得分达标（60/100）
        if top["score"] < 60:
            return
        outcome.opportunity = {
            "train_no": raw.train_no,
            "route": f"{raw.origin_city}→{raw.dest_city}",
            "depart": f"{raw.depart_date} {raw.depart_time}",
            "seat_class": raw.seat_class,
            "available": avail,
            "score": top["score"],
            "components": top["components"],
        }
        await self._emit(EventType.OPPORTUNITY_DETECTED, outcome,
                         payload={"train_no": raw.train_no,
                                  "score": top["score"]})
        await self._emit(EventType.NOTIFICATION_REQUESTED, outcome,
                         payload={"train_no": raw.train_no})
        if self.notifier is not None:
            self.notifier({
                "event_type": EventType.OPPORTUNITY_DETECTED.value,
                "task_id": task.id,
                "title": (f"火车机会: {raw.train_no} {raw.origin_city}→{raw.dest_city} "
                          f"{raw.depart_time} {raw.seat_class} 余票={avail}"),
                "material": {"train_no": raw.train_no,
                             "route": f"{raw.origin_city}→{raw.dest_city}",
                             "depart": raw.depart_time,
                             "seat_class": raw.seat_class,
                             "available": avail},
            })
        await self._emit(EventType.NOTIFICATION_SENT, outcome,
                         payload={"train_no": raw.train_no})
        outcome.notified = True

    async def _emit(self, event_type: EventType, outcome: RailwayScanOutcome,
                    payload: Optional[Dict] = None) -> None:
        from ...events import EventEnvelope
        envelope = EventEnvelope(
            event_type=event_type,
            trace_id=outcome.trace_id,
            task_id=outcome.task_id,
            source="railway_scan_coordinator",
            payload=payload or {},
        )
        outcome.emitted_events.append(event_type.value)
        await self.bus.publish(envelope)
