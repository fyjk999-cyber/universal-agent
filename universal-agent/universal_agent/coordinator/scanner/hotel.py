"""Hotel scan coordinator — parallel to flight, domain-isolated (RULE 3).

Separate event-driven pipeline for hotel domain. Bundle combination with
flight happens at the travel layer (see core.bundling), not inside either
domain scanner.
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
    RawHotel,
    TaskSpec,
    new_id,
)
from ...domains.hotel import entity_key, normalize_hotel, score_hotel
from ...events import EventBusProtocol, EventEnvelope, EventType
from ...memory import ObservationStore
from ...registry import SkillRegistry

log = logging.getLogger("ua.coordinator.hotel_scan")

#: source callable(query-ish) → list[RawHotel]
HotelFetcher = Callable[..., List[RawHotel]]


@dataclass
class HotelScanOutcome:
    trace_id: str
    task_id: str
    candidates: List[Candidate] = field(default_factory=list)
    offers: List[Offer] = field(default_factory=list)
    quotes: List[Quote] = field(default_factory=list)
    raw_hotels: List[RawHotel] = field(default_factory=list)
    best: Optional[RawHotel] = None
    emitted_events: List[str] = field(default_factory=list)


class HotelScanCoordinator:
    def __init__(self, *, bus: EventBusProtocol, registry: SkillRegistry,
                 observations: Optional[ObservationStore] = None,
                 fetchers: Optional[Dict[str, HotelFetcher]] = None) -> None:
        self.bus = bus
        self.registry = registry
        self.observations = observations
        self.fetchers = fetchers or {}

    async def scan(self, task: TaskSpec) -> HotelScanOutcome:
        trace_id = new_id("trace")
        outcome = HotelScanOutcome(trace_id=trace_id, task_id=task.id)
        await self._emit(EventType.SCAN_REQUESTED, outcome, task_id=task.id,
                         payload={"task_id": task.id, "trace_id": trace_id})

        raw_hotels: List[RawHotel] = []
        # 酒店按城市查询（复用 flight 的 destination 作为城市）
        cities = task.search_space.destination or []
        for city in cities:
            for marketplace_id, fetcher in self.fetchers.items():
                try:
                    batch = await asyncio.to_thread(fetcher, city)
                except Exception as exc:  # noqa: BLE001 — §48
                    log.warning("hotel source %s failed for %s: %s",
                                marketplace_id, city, exc)
                    if self.registry.get_marketplace(marketplace_id) is not None:
                        self.registry.set_marketplace_health(marketplace_id, "DEGRADED")
                    continue
                for raw in batch:
                    await self._emit(EventType.RAW_LISTING_DISCOVERED, outcome,
                                     payload={"hotel_id": raw.hotel_id,
                                              "source": raw.marketplace_id})
                    raw_hotels.append(raw)

        seen: Dict[str, str] = {}
        for raw in raw_hotels:
            cand, offer, quote, evidence = normalize_hotel(raw, task.id)
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
            outcome.raw_hotels.append(raw)
            await self._emit(EventType.QUOTE_OBSERVED, outcome,
                             payload={"offer_id": offer.offer_id,
                                      "price": quote.price.amount})

        if raw_hotels:
            prices = [r.price_per_night_cny for r in raw_hotels if r.price_per_night_cny > 0]
            mm = min(prices) if prices else 0.0
            scored = [(r, score_hotel(r, mm)["total"]) for r in raw_hotels]
            scored.sort(key=lambda x: x[1], reverse=True)
            outcome.best = scored[0][0] if scored else None

        await self._emit(EventType.SCAN_COMPLETED, outcome,
                         payload={"hotels": len(raw_hotels)})
        return outcome

    async def _emit(self, event_type: EventType, outcome: HotelScanOutcome,
                    task_id: Optional[str] = None, payload: Optional[Dict] = None) -> None:
        envelope = EventEnvelope(
            event_type=event_type,
            trace_id=outcome.trace_id,
            task_id=task_id or outcome.task_id,
            source="hotel_scan_coordinator",
            payload=payload or {},
        )
        outcome.emitted_events.append(event_type.value)
        await self.bus.publish(envelope)
