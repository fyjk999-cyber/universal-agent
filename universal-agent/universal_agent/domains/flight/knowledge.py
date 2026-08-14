"""Flight domain knowledge (RULE 3: domain knows domain facts, not platforms).

Entity Resolution key (§21) for flights:
    date | flight_numbers | origin | destination | departure_time
Two sources seeing the same real object must produce the same key.
"""
from __future__ import annotations

from typing import List

from ...core.contracts import RawListing, RawSegment


def flight_numbers(listing: RawListing) -> List[str]:
    out: List[str] = []
    for seg in listing.outbound.segments + listing.inbound.segments:
        if seg.flight_no not in out:
            out.append(seg.flight_no)
    return out


def entity_key(listing: RawListing) -> str:
    """Deterministic entity key: same real itinerary → same key."""
    fns = "|".join(flight_numbers(listing))
    return "|".join([
        listing.depart_date,
        fns,
        listing.origin_airport,
        listing.dest_airport,
        listing.outbound.segments[0].dep_time if listing.outbound.segments else "",
    ])


def candidate_attributes(listing: RawListing) -> dict:
    return {
        "origin": listing.origin_airport,
        "destination": listing.dest_airport,
        "depart_date": listing.depart_date,
        "return_date": listing.return_date,
        "nights": listing.nights,
        "stops_total": listing.outbound.stops + listing.inbound.stops,
        "total_duration_min": listing.outbound.total_min + listing.inbound.total_min,
        "outbound_flight_numbers": flight_numbers(listing),
    }


def segment_label(seg: RawSegment) -> str:
    return f"{seg.airline}{seg.flight_no} {seg.dep_airport}→{seg.arr_airport}"
