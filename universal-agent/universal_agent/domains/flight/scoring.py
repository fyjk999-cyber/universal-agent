"""Deterministic flight scoring (RULE 7: programmatic, no LLM).

Scoring dimensions (0–100 each), weighted:
  price, stops, layover, total_time, quality
Weights come from a frozen default config (task may override later).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ...core.contracts import RawListing

RELIABLE_AIRLINES = {
    "CA", "MU", "CZ", "HU", "MF", "3U", "ZH",
    "NZ", "QF", "SQ", "CX", "KA", "JL", "NH", "KE", "OZ", "TG", "MH",
    "LH", "KL", "AF", "BA", "AY", "EK", "EY", "QR", "TK", "AC", "UA",
}


@dataclass(frozen=True)
class FlightScoreConfig:
    price_weight: float = 0.35
    stops_weight: float = 0.20
    layover_weight: float = 0.15
    total_time_weight: float = 0.15
    quality_weight: float = 0.15

    layover_ideal_min: int = 90
    layover_ideal_max: int = 240
    layover_accept_min: int = 60
    layover_accept_max: int = 480
    max_stops: int = 1
    max_layover_min: int = 480
    max_total_hours: int = 40


DEFAULT_FLIGHT_CFG = FlightScoreConfig()


def clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def price_score(price: float, market_min: float) -> float:
    if market_min <= 0:
        return 50.0
    ratio = price / market_min
    if ratio <= 1.0:
        return 100.0
    if ratio <= 1.10:
        return 100 - (ratio - 1.0) / 0.10 * 15
    if ratio <= 1.60:
        return 85 - (ratio - 1.10) / 0.50 * 45
    return clamp(40 - (ratio - 1.60) / 1.0 * 20)


def stops_score(listing: RawListing) -> float:
    stops = listing.outbound.stops + listing.inbound.stops
    if stops == 0:
        return 100.0
    if stops == 1:
        return 60.0
    return 20.0


def layover_score(listing: RawListing, cfg: FlightScoreConfig = DEFAULT_FLIGHT_CFG) -> float:
    """Worst layover across both directions."""
    worst: Optional[float] = None

    def one(leg) -> Optional[float]:
        if not leg.layovers:
            return 100.0
        s: Optional[float] = None
        for lay in leg.layovers:
            if cfg.layover_ideal_min <= lay <= cfg.layover_ideal_max:
                v = 100.0
            elif cfg.layover_accept_min <= lay < cfg.layover_ideal_min:
                v = 100 - (cfg.layover_ideal_min - lay) / (cfg.layover_ideal_min - cfg.layover_accept_min) * 40
            elif cfg.layover_ideal_max < lay <= cfg.layover_accept_max:
                v = 100 - (lay - cfg.layover_ideal_max) / (cfg.layover_accept_max - cfg.layover_ideal_max) * 40
            else:
                v = 30.0 if lay <= 8 * 60 else 10.0
            if leg.overnight_layover:
                v = min(v, 25.0)
            if leg.airport_change:
                v = min(v, 15.0)
            if leg.self_transfer:
                v = min(v, 5.0)
            s = v if s is None else min(s, v)
        return s

    for leg in (listing.outbound, listing.inbound):
        v = one(leg)
        if v is not None:
            worst = v if worst is None else min(worst, v)
    return worst if worst is not None else 100.0


def total_time_score(listing: RawListing) -> float:
    total_h = (listing.outbound.total_min + listing.inbound.total_min) / 60.0
    if total_h <= 20:
        return 100.0
    if total_h <= 30:
        return 100 - (total_h - 20) / 10 * 25
    if total_h <= 45:
        return 75 - (total_h - 30) / 15 * 35
    return clamp(40 - (total_h - 45) / 15 * 20)


def quality_score(listing: RawListing) -> float:
    score = 70.0
    airlines = {s.airline for s in listing.outbound.segments + listing.inbound.segments}
    if airlines & RELIABLE_AIRLINES:
        score += 6
    checked = listing.luggage.get("checked")
    if checked not in (None, "", "0", "0kg", "不含"):
        score += 4
    else:
        score -= 6
    first = listing.outbound.segments[0] if listing.outbound.segments else None
    if first:
        try:
            h = int(first.dep_time.split(":")[0])
            score += 3 if 6 <= h <= 22 else -5
        except (ValueError, AttributeError):
            pass
    if listing.outbound.self_transfer or listing.inbound.self_transfer:
        score -= 25
    if listing.outbound.airport_change or listing.inbound.airport_change:
        score -= 15
    if listing.outbound.overnight_layover or listing.inbound.overnight_layover:
        score -= 20
    if listing.outbound.stops + listing.inbound.stops == 0:
        score += 10
    return clamp(score)


def score_listing(listing: RawListing, market_min: float,
                  cfg: FlightScoreConfig = DEFAULT_FLIGHT_CFG) -> Dict[str, float]:
    """Return {'total': ..., 'components': {...}}."""
    p = price_score(listing.price_cny, market_min)
    s = stops_score(listing)
    l = layover_score(listing, cfg)
    t = total_time_score(listing)
    q = quality_score(listing)
    total = (
        p * cfg.price_weight + s * cfg.stops_weight + l * cfg.layover_weight
        + t * cfg.total_time_weight + q * cfg.quality_weight
    )
    return {
        "total": round(total, 1),
        "components": {"price": round(p, 1), "stops": round(s, 1),
                       "layover": round(l, 1), "total_time": round(t, 1),
                       "quality": round(q, 1)},
    }
