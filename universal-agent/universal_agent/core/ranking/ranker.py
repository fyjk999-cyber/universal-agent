"""Deterministic Top-N ranking (RULE 7, §61 Top5).

Pure function: given scored candidates, pick Top N with diversity —
  best overall / lowest price / shortest total time / best per-origin.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from ...core.contracts import RawListing


def rank_top_n(listings: List[RawListing],
               scored: Dict[str, Dict[str, float]],
               top_n: int = 5) -> List[RawListing]:
    """Input: raw listings + {listing_id: score dict}; output: top N ordered."""
    if not listings:
        return []

    def key(l: RawListing) -> float:
        return scored.get(l.listing_id, {}).get("total", 0.0)

    ordered = sorted(listings, key=key, reverse=True)
    picks: List[RawListing] = []

    def add(l: Optional[RawListing]) -> None:
        if l and all(l.listing_id != p.listing_id for p in picks):
            picks.append(l)

    add(ordered[0] if ordered else None)
    add(min(listings, key=lambda x: (x.price_cny, -key(x))) if listings else None)
    add(min(listings, key=lambda x: (x.outbound.total_min + x.inbound.total_min, -key(x)))
        if listings else None)
    # one best per origin (HGH / PVG / SHA) for representative coverage
    for origin in sorted({l.origin_airport for l in listings}):
        if len(picks) >= top_n:
            break
        origin_best = [l for l in ordered if l.origin_airport == origin]
        if origin_best:
            add(origin_best[0])
    # fill remaining with next-best not yet picked
    for l in ordered:
        if len(picks) >= top_n:
            break
        add(l)
    return picks[:top_n]
