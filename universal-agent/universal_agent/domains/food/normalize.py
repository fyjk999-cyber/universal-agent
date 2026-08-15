"""Food Domain（P19）— 菜品标准化。"""
from __future__ import annotations

from typing import Tuple

from ...core.contracts import (
    Candidate,
    Evidence,
    Money,
    Offer,
    Quote,
    RawDish,
    new_id,
)


def entity_key(raw: "RawDish") -> str:
    return f"{raw.restaurant}|{raw.dish_name}"


def normalize_dish(raw: RawDish, task_id: str) -> Tuple[Candidate, Offer, Quote, Evidence]:
    key = entity_key(raw)
    candidate = Candidate(
        candidate_id=new_id("dcand"), domain="food", task_id=task_id,
        entity_key=key,
        attributes={"restaurant": raw.restaurant, "dish_name": raw.dish_name},
        source_ids=[raw.marketplace_id], is_verified=False,
    )
    offer = Offer(
        offer_id=new_id("doff"), candidate_id=candidate.candidate_id,
        marketplace_id=raw.marketplace_id,
        terms={"restaurant": raw.restaurant, "dish_name": raw.dish_name},
    )
    quote = Quote(
        quote_id=new_id("dquote"), offer_id=offer.offer_id,
        price=Money(amount=raw.price_cny, currency=raw.currency),
        method="search", confidence=0.9, source=raw.marketplace_id,
    )
    evidence = Evidence(
        evidence_id=new_id("devid"), field="price", value=raw.price_cny,
        source=raw.marketplace_id, method="search_result",
        snapshot_reference=raw.dish_id, confidence=0.9,
    )
    return candidate, offer, quote, evidence
