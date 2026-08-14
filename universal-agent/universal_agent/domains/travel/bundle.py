"""Travel composite domain (§26) — combines Flight + Hotel into bundles.

This layer owns cross-domain combination ONLY; it knows nothing about
platforms or how to fetch anything (RULE 3).
"""
from __future__ import annotations

from typing import List, Optional

from ...core.bundling import (
    BundleComponent,
    BundleResult,
    best_bundle,
    build_bundles,
)
from ...core.contracts import RawHotel, RawListing
from ...domains.flight.scoring import score_listing
from ...domains.hotel import entity_key as hotel_key
from ...domains.hotel import normalize_hotel, score_hotel
from ...domains.flight import entity_key as flight_key
from ...domains.flight import normalize_listing


def compose_travel_bundle(flights: List[RawListing],
                          hotels: Optional[List[RawHotel]] = None,
                          task_id: str = "t1",
                          max_hotels: int = 3,
                          valid_pair=None) -> BundleResult:
    """Build Flight+Hotel bundles from scan outcomes (§28).

    - flights: already-scored RawListing from flight scan
    - hotels: RawHotel from hotel scan (optional)
    Uses deterministic domain scorers; no LLM, no platform knowledge.
    """
    if not flights:
        return BundleResult(bundles=[], notes=["no flights"])

    f_prices = [f.price_cny for f in flights if f.price_cny > 0]
    f_min = min(f_prices) if f_prices else 0.0

    flight_components = [
        BundleComponent(
            candidate_id=flight_key(f),
            domain="flight",
            price=f.price_cny,
            score=score_listing(f, f_min)["total"],
            nights=0,
        ) for f in flights
    ]

    if not hotels:
        return build_bundles(flight_components, hotels=None, task_id=task_id)

    h_prices = [h.price_per_night_cny for h in hotels if h.price_per_night_cny > 0]
    h_min = min(h_prices) if h_prices else 0.0

    # 酒店去重（entity key）后取评分最高前 N
    seen: set = set()
    hotel_components: List[BundleComponent] = []
    for h in hotels:
        key = hotel_key(h)
        if key in seen:
            continue
        seen.add(key)
        hotel_components.append(BundleComponent(
            candidate_id=key,
            domain="hotel",
            price=h.price_per_night_cny,
            score=score_hotel(h, h_min)["total"],
            nights=h.nights or 1,
        ))
    hotel_components.sort(key=lambda c: c.score, reverse=True)
    hotel_components = hotel_components[:max_hotels]

    return build_bundles(flight_components, hotel_components, task_id=task_id,
                         valid_pair=valid_pair)


__all__ = ["best_bundle", "compose_travel_bundle"]
