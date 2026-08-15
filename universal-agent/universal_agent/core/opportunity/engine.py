"""Opportunity Engine (§32) — deterministic, evidence-based.

First phase: no prediction. Computes from stable observations:
  Historical Low / Absolute Drop / Percent Drop / Price Percentile /
  Candidate Score / Offer Trust / Verification Confidence
→ OpportunityScore (0–100).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from ...core.contracts import OpportunityScore, Quote, new_id


@dataclass
class OpportunityInput:
    quotes: List[Quote]           # full history for this offer/candidate
    current_price: float
    candidate_score: float = 70.0
    offer_trust: float = 0.9
    verification_confidence: float = 0.85
    historical_low_buffer_cny: float = 50.0
    availability: str = "UNKNOWN"   # P11: HIGH | MEDIUM | LOW | UNKNOWN
    trend: Optional[dict] = None    # P11: {"momentum":..., "volatility":...} estimate


def _percentile(value: float, values: List[float]) -> float:
    """Percentile of value within historical values (0-100, lower=cheaper)."""
    if not values:
        return 100.0
    below = sum(1 for v in values if v <= value)
    return below / len(values) * 100.0


def compute_opportunity(inp: OpportunityInput) -> OpportunityScore:
    prices = [q.price.amount for q in inp.quotes] or [inp.current_price]
    hist_min = min(prices)
    hist_max = max(prices)

    absolute_drop = max(0.0, hist_max - inp.current_price)
    percent_drop = (absolute_drop / hist_max * 100.0) if hist_max else 0.0
    is_hist_low = inp.current_price <= hist_min + inp.historical_low_buffer_cny
    percentile = _percentile(inp.current_price, prices)

    # deterministic opportunity score: weighted blend
    low_bonus = 30.0 if is_hist_low else 0.0
    drop_component = min(40.0, percent_drop * 2.0)          # up to 40 pts
    score_component = inp.candidate_score * 0.25            # up to 25 pts
    trust_component = inp.offer_trust * 20.0                # up to 20 pts
    verif_component = inp.verification_confidence * 15.0    # up to 15 pts
    # P11: availability（库存风险）→ 机会分提升
    avail_component = {"LOW": 8.0, "MEDIUM": 4.0, "HIGH": 0.0}.get(inp.availability, 0.0)
    total = min(100.0, low_bonus + drop_component + score_component
                + trust_component + verif_component + avail_component)

    # P11: trend 仅作 estimate 传递，不改变历史判定
    trend_out = dict(inp.trend or {})
    trend_out["is_estimate"] = True

    return OpportunityScore(
        score_id=new_id("opp"),
        target_key=inp.quotes[0].offer_id if inp.quotes else "",
        score_type="opportunity",
        components={
            "low_bonus": round(low_bonus, 1),
            "drop": round(drop_component, 1),
            "candidate_score": round(score_component, 1),
            "trust": round(trust_component, 1),
            "verification": round(verif_component, 1),
            "availability": round(avail_component, 1),
        },
        total_score=round(total, 1),
        historical_low=is_hist_low,
        absolute_drop_cny=round(absolute_drop, 2),
        percent_drop=round(percent_drop, 2),
        price_percentile=round(percentile, 2),
        candidate_score=inp.candidate_score,
        offer_trust=inp.offer_trust,
        verification_confidence=inp.verification_confidence,
        availability=inp.availability,
        trend=trend_out,
    )
