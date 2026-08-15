"""Hotel normalizer — RawHotel → Candidate + Offer + Quote + Evidence (§63)."""
from __future__ import annotations

from typing import Tuple

from ...core.contracts import (
    Candidate,
    Evidence,
    Money,
    Offer,
    Quote,
    RawHotel,
    new_id,
)
from .knowledge import entity_key, normalize_policy, normalize_room


def normalize_hotel(raw: RawHotel, task_id: str) -> Tuple[Candidate, Offer, Quote, Evidence]:
    """Turn one raw hotel offer into (candidate, offer, quote, price_evidence)."""
    key = entity_key(raw)
    norm = normalize_room(raw.room_name)
    policy = normalize_policy(raw)  # P9: 政策归一化（breakfast/cancellation/tax/occupancy）

    candidate = Candidate(
        candidate_id=new_id("hcand"),
        domain="hotel",
        task_id=task_id,
        entity_key=key,
        attributes={
            "name": raw.name,
            "city": raw.city,
            "brand": raw.brand,
            "lat": raw.lat,
            "lng": raw.lng,
            "rating": raw.rating,
            "room_grade": norm.room_grade,
            "bed_type": norm.bed_type,
            "board": norm.board,
        },
        source_ids=[raw.marketplace_id],
        is_verified=False,
    )

    offer = Offer(
        offer_id=new_id("hoff"),
        candidate_id=candidate.candidate_id,
        marketplace_id=raw.marketplace_id,
        terms={
            "check_in": raw.check_in,
            "check_out": raw.check_out,
            "nights": raw.nights,
            "room": raw.room_name,
            "room_grade": norm.room_grade,
            "board": norm.board,
            # P9: 政策
            "breakfast": policy.breakfast,
            "cancellation": policy.cancellation,
            "tax": policy.tax,
            "occupancy_max": policy.occupancy_max,
        },
        url=raw.url,
    )

    quote = Quote(
        quote_id=new_id("hquote"),
        offer_id=offer.offer_id,
        price=Money(amount=raw.price_per_night_cny, currency=raw.currency),
        method="search",
        confidence=0.9 if raw.currency == "CNY" else 0.7,
        snapshot_reference=raw.hotel_id,
        source=raw.marketplace_id,
    )

    evidence = Evidence(
        evidence_id=new_id("hevid"),
        field="price_per_night",
        value=raw.price_per_night_cny,
        source=raw.marketplace_id,
        method="search_result",
        snapshot_reference=raw.hotel_id,
        confidence=quote.confidence,
    )

    return candidate, offer, quote, evidence
