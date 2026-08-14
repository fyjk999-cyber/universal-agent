"""Shadow Scan Coordinator (§61, §62, §69) — event-driven flight scan pipeline.

Flow (SHADOW MODE, no purchase):
  SCAN_REQUESTED
    → for each source: RAW_LISTING_DISCOVERED
    → Normalize → CANDIDATE_CREATED + OFFER_DISCOVERED + QUOTE_OBSERVED
    → Dedup/merge by entity_key
    → Score → SCORE_UPDATED
    → Change detection → MATERIAL_CHANGE_DETECTED
    → Opportunity → OPPORTUNITY_DETECTED
    → Trigger eval → NOTIFICATION_REQUESTED / NOTIFICATION_SENT

All events share one trace_id so the whole scan is replayable (§51, §72).
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from ...core.contracts import (
    Candidate,
    Money,
    Offer,
    OpportunityScore,
    Quote,
    RawListing,
    TaskSpec,
    VerificationResult,
    new_id,
    utc_now,
)
from ...core.ranking import rank_top_n
from ...core.change_detection import detect_material_change
from ...core.opportunity import OpportunityInput, compute_opportunity
from ...core.verification import FlightVerifier
from ...domains.flight import entity_key, normalize_listing
from ...domains.flight.scoring import score_listing
from ...events import EventBusProtocol, EventEnvelope, EventType
from ...memory import ObservationStore
from ...notifications import NotificationDedup
from ...registry import SkillRegistry
from ..query_planner import FlightQuery, build_query_plan
from ..source_planner import plan_sources
from ..task_registry import TaskRegistry

log = logging.getLogger("ua.coordinator.scanner")

#: A source is any callable(query) → list[RawListing]
RawListingFetcher = Callable[[FlightQuery], List[RawListing]]


@dataclass
class ScanOutcome:
    trace_id: str
    task_id: str
    candidates: List[Candidate] = field(default_factory=list)
    offers: List[Offer] = field(default_factory=list)
    quotes: List[Quote] = field(default_factory=list)
    raw_listings: List[RawListing] = field(default_factory=list)
    top5: List[RawListing] = field(default_factory=list)
    opportunity: Optional[OpportunityScore] = None
    verification: Optional[VerificationResult] = None
    notified: bool = False
    emitted_events: List[str] = field(default_factory=list)

    def summary(self) -> Dict:
        return {
            "trace_id": self.trace_id,
            "task_id": self.task_id,
            "raw_listings": len(self.raw_listings),
            "candidates": len(self.candidates),
            "quotes": len(self.quotes),
            "top5": [f"{r.origin_airport}→{r.dest_airport} ¥{r.price_cny:.0f}"
                     for r in self.top5],
            "notified": self.notified,
        }


class ShadowScanCoordinator:
    """Runs one full shadow scan and emits the whole event chain."""

    def __init__(self, *, bus: EventBusProtocol, registry: SkillRegistry,
                 task_registry: Optional[TaskRegistry] = None,
                 observations: Optional[ObservationStore] = None,
                 dedup: Optional[NotificationDedup] = None,
                 fetchers: Optional[Dict[str, RawListingFetcher]] = None,
                 max_queries: int = 60) -> None:
        self.bus = bus
        self.registry = registry
        self.task_registry = task_registry
        self.observations = observations
        self.dedup = dedup or NotificationDedup()
        self.fetchers = fetchers or {}
        self.max_queries = max_queries

    # ------------------------------------------------------------------ API
    async def scan(self, task: TaskSpec) -> ScanOutcome:
        trace_id = new_id("trace")
        outcome = ScanOutcome(trace_id=trace_id, task_id=task.id)
        await self._emit(EventType.SCAN_REQUESTED, outcome, task_id=task.id,
                         payload={"task_id": task.id, "trace_id": trace_id})

        plan = build_query_plan(task, max_queries=self.max_queries)
        source_plan = plan_sources(task.id, domain="flight", registry=self.registry)

        raw_listings: List[RawListing] = []
        for query in plan.queries:
            for marketplace in source_plan.sources:
                fetcher = self.fetchers.get(marketplace.id)
                if fetcher is None:
                    continue
                try:
                    # 同步 fetcher（浏览器/HTTP）在 asyncio 内通过 to_thread 执行，
                    # 避免 Playwright Sync API 在事件循环中被拒绝
                    batch = await asyncio.to_thread(fetcher, query)
                except Exception as exc:  # noqa: BLE001 — §48 source failure
                    log.warning("source %s failed for %s: %s",
                                marketplace.id, query.origin, exc)
                    # §53: 源失败 → 标记 DEGRADED，后续跳过该源
                    if self.registry.get_marketplace(marketplace.id) is not None:
                        self.registry.set_marketplace_health(marketplace.id, "DEGRADED")
                    continue
                for listing in batch:
                    await self._emit(EventType.RAW_LISTING_DISCOVERED, outcome,
                                     payload={"listing_id": listing.listing_id,
                                              "source": listing.marketplace_id})
                    raw_listings.append(listing)

        # ---- normalize + dedup by entity key ----
        seen: Dict[str, str] = {}  # entity_key -> candidate_id
        for listing in raw_listings:
            cand, offer, quote, evidence = normalize_listing(listing, task.id)
            key = entity_key(listing)
            quote.source = listing.marketplace_id
            if key in seen:
                cand.candidate_id = seen[key]  # merge into same candidate (§21)
                offer.candidate_id = cand.candidate_id
            else:
                seen[key] = cand.candidate_id
                outcome.candidates.append(cand)
                await self._emit(EventType.CANDIDATE_CREATED, outcome,
                                 payload={"candidate_id": cand.candidate_id,
                                          "entity_key": key})
            outcome.offers.append(offer)
            outcome.quotes.append(quote)
            outcome.raw_listings.append(listing)
            await self._emit(EventType.OFFER_DISCOVERED, outcome,
                             payload={"offer_id": offer.offer_id})
            await self._emit(EventType.QUOTE_OBSERVED, outcome,
                             payload={"offer_id": offer.offer_id,
                                      "price": quote.price.amount})
            if self.observations is not None:
                # record by stable entity key so multi-round history accumulates
                self.observations.record_price(quote, task.id, domain="flight",
                                               entity_key=key)

        # ---- score + rank ----
        prices = [r.price_cny for r in raw_listings if r.price_cny > 0]
        market_min = min(prices) if prices else 0.0
        scored: Dict[str, Dict[str, float]] = {}
        for listing in raw_listings:
            res = score_listing(listing, market_min)
            scored[listing.listing_id] = res
        outcome.top5 = rank_top_n(raw_listings, scored, top_n=5)
        await self._emit(EventType.SCORE_UPDATED, outcome,
                         payload={"market_min": market_min,
                                  "top5": [r.listing_id for r in outcome.top5]})

        # ---- change detection + opportunity + verification on best candidate ----
        if outcome.quotes:
            best = outcome.top5[0] if outcome.top5 else None
            best_quote = None
            best_entity_key = None
            if best is not None:
                for listing in outcome.raw_listings:
                    if listing.listing_id == best.listing_id:
                        best_entity_key = entity_key(listing)
                        break
                for q in outcome.quotes:
                    if q.offer_id == _offer_for_listing(best, outcome.offers):
                        best_quote = q
                        break

            if best_quote is not None and self.observations is not None:
                # cross-source agreement: how many distinct sources saw this offer
                cross_sources = {
                    q.source for q in outcome.quotes
                    if q.offer_id == best_quote.offer_id
                }
                agreement = len(cross_sources) >= 2

                # change detection against PRIOR observation (this scan's quote
                # is already in history; compare with the one before it)
                hist = self.observations.price_history(best_entity_key or best_quote.offer_id)
                prev_price = hist[-2] if len(hist) >= 2 else None
                if prev_price is not None:
                    prev_q = Quote(quote_id="prev", offer_id=best_quote.offer_id,
                                   price=Money(amount=prev_price))
                    change = detect_material_change(best_quote, prev_q)
                else:
                    change = detect_material_change(best_quote, None)
                await self._emit(EventType.MATERIAL_CHANGE_DETECTED, outcome,
                                 payload={"offer_id": best_quote.offer_id,
                                          "changed": change.changed,
                                          "delta_cny": change.delta_cny})

                # tiered verification (§31, §62): T2 with cross-source promotion
                verifier = FlightVerifier()
                verification = verifier.verify(
                    target_key=best_entity_key or best_quote.offer_id,
                    offer_id=best_quote.offer_id,
                    quotes=[q for q in outcome.quotes
                            if q.offer_id == best_quote.offer_id],
                    cross_source_agreement=agreement,
                    tier="T2",
                )
                outcome.verification = verification
                await self._emit(EventType.VERIFICATION_COMPLETED, outcome,
                                 payload={"verification_id": verification.verification_id,
                                          "passed": verification.passed,
                                          "confidence": verification.confidence.final_confidence})

                # opportunity from full entity history (§32)
                history_quotes = self.observations.quotes_history(
                    best_entity_key or best_quote.offer_id)
                opp = compute_opportunity(OpportunityInput(
                    quotes=history_quotes or [best_quote],
                    current_price=best_quote.price.amount,
                    candidate_score=scored.get(best.listing_id, {}).get("total", 70.0),
                    offer_trust=0.9,
                    verification_confidence=verification.confidence.final_confidence,
                ))
                outcome.opportunity = opp
                await self._emit(EventType.OPPORTUNITY_DETECTED, outcome,
                                 payload={"score": opp.total_score,
                                          "historical_low": opp.historical_low})

        # ---- trigger + notify (with dedup) ----
        outcome.notified = await self._maybe_notify(task, outcome)
        await self._emit(EventType.SCAN_COMPLETED, outcome,
                         payload={"summary": outcome.summary()})
        return outcome

    async def _maybe_notify(self, task: TaskSpec, outcome: ScanOutcome) -> bool:
        if not outcome.top5 or outcome.opportunity is None:
            return False
        rules = task.notify_if
        opp = outcome.opportunity
        top = outcome.top5[0]

        reasons: List[str] = []
        if rules.opportunity_score_gte is not None and opp.total_score >= rules.opportunity_score_gte:
            reasons.append(f"机会分 {opp.total_score} ≥ {rules.opportunity_score_gte}")
        if rules.historical_low and opp.historical_low:
            reasons.append("历史最低价")
        if rules.price_drop_cny_gte is not None and opp.absolute_drop_cny >= rules.price_drop_cny_gte:
            reasons.append(f"降价 ¥{opp.absolute_drop_cny:.0f} ≥ ¥{rules.price_drop_cny_gte}")
        if rules.price_drop_percent_gte is not None and opp.percent_drop >= rules.price_drop_percent_gte:
            reasons.append(f"降价 {opp.percent_drop:.1f}% ≥ {rules.price_drop_percent_gte}%")

        if not reasons:
            return False

        # dedup: identical material within cooldown is suppressed (§34)
        material = {"origin": top.origin_airport, "dest": top.dest_airport,
                    "price": top.price_cny, "depart": top.depart_date}
        if not self.dedup.should_notify(task.id, top.listing_id, material):
            outcome.emitted_events.append("NOTIFICATION_SUPPRESSED")
            return False

        self.dedup.record(task.id, top.listing_id, material)
        await self._emit(EventType.NOTIFICATION_REQUESTED, outcome,
                         payload={"listing_id": top.listing_id,
                                  "price": top.price_cny, "reasons": reasons})
        await self._emit(EventType.NOTIFICATION_SENT, outcome,
                         payload={"listing_id": top.listing_id,
                                  "price": top.price_cny})
        return True

    # ------------------------------------------------------------------ util
    async def _emit(self, event_type: EventType, outcome: ScanOutcome,
                    task_id: Optional[str] = None, payload: Optional[Dict] = None) -> None:
        envelope = EventEnvelope(
            event_type=event_type,
            trace_id=outcome.trace_id,
            task_id=task_id or outcome.task_id,
            source="shadow_scan_coordinator",
            payload=payload or {},
        )
        outcome.emitted_events.append(event_type.value)
        await self.bus.publish(envelope)


def _offer_for_listing(listing: RawListing, offers: List[Offer]) -> Optional[str]:
    for o in offers:
        if o.terms.get("depart_date") == listing.depart_date and \
           o.terms.get("origin") == listing.origin_airport and \
           o.terms.get("destination") == listing.dest_airport and \
           abs(float(o.terms.get("total_duration_min", 0)) -
               (listing.outbound.total_min + listing.inbound.total_min)) < 60:
            return o.offer_id
    return None
