"""Flight normalizer — RawListing → Candidate + Offer + Quote + Evidence (§20, §30).

Deterministic, pure functions. RULE 7/8: no LLM in the data chain; every
key fact carries evidence (source, method, timestamp, confidence).
"""
from __future__ import annotations

from typing import Tuple

from ...core.contracts import (
    Candidate,
    CandidateEnvelope,
    Evidence,
    Money,
    Offer,
    Quote,
    RawListing,
    new_id,
)
from .knowledge import candidate_attributes, entity_key


def normalize_listing(listing: RawListing, task_id: str) -> Tuple[Candidate, Offer, Quote, Evidence]:
    """Turn one raw listing into (candidate, offer, quote, price_evidence)."""
    key = entity_key(listing)
    candidate = Candidate(
        candidate_id=new_id("cand"),
        domain="flight",
        task_id=task_id,
        entity_key=key,
        attributes=candidate_attributes(listing),
        source_ids=[listing.marketplace_id],
        is_verified=False,
    )

    offer = Offer(
        offer_id=new_id("offer"),
        candidate_id=candidate.candidate_id,
        marketplace_id=listing.marketplace_id,
        terms={
            "origin": listing.origin_airport,
            "destination": listing.dest_airport,
            "depart_date": listing.depart_date,
            "return_date": listing.return_date,
            "nights": listing.nights,
            "luggage": listing.luggage,
            "stops_total": listing.outbound.stops + listing.inbound.stops,
            "total_duration_min": listing.outbound.total_min + listing.inbound.total_min,
        },
        url=listing.url,
    )

    quote = Quote(
        quote_id=new_id("quote"),
        offer_id=offer.offer_id,
        price=Money(amount=listing.price_cny, currency=listing.currency),
        method="search",
        confidence=0.9 if listing.currency == "CNY" else 0.7,
        snapshot_reference=listing.listing_id,
    )

    evidence = Evidence(
        evidence_id=new_id("evid"),
        field="price",
        value=listing.price_cny,
        source=listing.marketplace_id,
        method="search_result",
        snapshot_reference=listing.listing_id,
        confidence=quote.confidence,
    )

    return candidate, offer, quote, evidence


def to_envelope(candidate: Candidate, source: str) -> CandidateEnvelope:
    return CandidateEnvelope(candidate=candidate, source=source)
