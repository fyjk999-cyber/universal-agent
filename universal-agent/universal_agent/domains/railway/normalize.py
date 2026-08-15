"""Railway Domain（P17）— 火车票标准化。

复用 Core Candidate/Offer/Quote 契约；不触碰 Core。
"""
from __future__ import annotations

from typing import Tuple

from ...core.contracts import (
    Candidate,
    Evidence,
    Money,
    Offer,
    Quote,
    RawRailway,
    new_id,
)


def entity_key(raw: "RawRailway") -> str:
    return f"{raw.train_no}|{raw.origin_city}|{raw.dest_city}|{raw.depart_date}"


def normalize_railway(raw: RawRailway, task_id: str) -> Tuple[Candidate, Offer, Quote, Evidence]:
    key = entity_key(raw)
    candidate = Candidate(
        candidate_id=new_id("rcand"), domain="railway", task_id=task_id,
        entity_key=key,
        attributes={
            "train_no": raw.train_no, "origin_city": raw.origin_city,
            "dest_city": raw.dest_city, "depart_date": raw.depart_date,
            "depart_time": raw.depart_time, "arrive_time": raw.arrive_time,
            "seat_class": raw.seat_class,
        },
        source_ids=[raw.marketplace_id], is_verified=False,
    )
    offer = Offer(
        offer_id=new_id("roff"), candidate_id=candidate.candidate_id,
        marketplace_id=raw.marketplace_id,
        terms={"train_no": raw.train_no, "seat_class": raw.seat_class},
    )
    quote = Quote(
        quote_id=new_id("rquote"), offer_id=offer.offer_id,
        price=Money(amount=raw.price_cny, currency=raw.currency),
        method="search", confidence=0.9, source=raw.marketplace_id,
    )
    evidence = Evidence(
        evidence_id=new_id("revid"), field="price", value=raw.price_cny,
        source=raw.marketplace_id, method="search_result",
        snapshot_reference=raw.railway_id, confidence=0.9,
    )
    return candidate, offer, quote, evidence
