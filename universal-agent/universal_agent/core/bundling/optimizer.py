"""Bundle Optimizer (§28) — TOTAL TRIP UTILITY, not per-component greed.

Key insight: 机票A便宜但酒店贵；机票B贵¥300但酒店便宜¥1200
→ 必须比较总成本 + 总效用，而不是分别挑最低机票、最低酒店。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from ...core.contracts import BundleCandidate, new_id


@dataclass
class BundleComponent:
    """One candidate with its price + score (domain-agnostic)."""
    candidate_id: str
    domain: str
    price: float
    score: float = 70.0
    nights: int = 0  # hotel only, for total-cost math


@dataclass
class BundleResult:
    bundles: List[BundleCandidate]
    notes: List[str]


def build_bundles(flights: List[BundleComponent],
                  hotels: Optional[List[BundleComponent]] = None,
                  task_id: str = "t1",
                  price_weight: float = 0.6,
                  score_weight: float = 0.4,
                  valid_pair=None) -> BundleResult:
    """Cross-product flights × hotels into bundles, sorted by utility.

    Utility = weighted blend of normalized total cost (cheaper better) and
    composite score (quality). Returns the best bundles — never just the
    cheapest flight + cheapest hotel independently.

    `valid_pair(flight, hotel) -> bool` 可选组合约束（日期/区域绑定）；
    无约束时成本线性可分，独立贪心即最优；有约束时按总效用选优（§28）。
    """
    notes: List[str] = []
    if not flights:
        return BundleResult(bundles=[], notes=["no flights"])

    # flight-only bundles (when no hotel or hotel missing)
    if not hotels:
        out = []
        for f in flights:
            out.append(BundleCandidate(
                bundle_id=new_id("bnd"),
                task_id=task_id,
                components={"flight": f.candidate_id},
                cost={"flight": f.price, "total": f.price},
                score=f.score,
            ))
        out.sort(key=lambda b: b.score, reverse=True)
        return BundleResult(bundles=out, notes=notes)

    min_total = _min_total(flights, hotels)
    max_total = _max_total(flights, hotels)
    span = max(1.0, max_total - min_total)

    # 独立贪心组合（分别最低）：§28 说明这并不总是最优
    greedy_flight = min(flights, key=lambda x: x.price)
    greedy_hotel = min(hotels, key=lambda x: x.price)
    greedy_total = greedy_flight.price + greedy_hotel.price * greedy_hotel.nights

    bundles: List[BundleCandidate] = []
    best_so_far: Optional[float] = None
    for f in flights:
        for h in hotels:
            # 可选组合约束（如日期/区域绑定）：不满足的组合排除
            if valid_pair is not None and not valid_pair(f, h):
                continue
            total = f.price + h.price * h.nights
            # 归一化总成本分：最便宜=100
            cost_score = 100.0 if span < 1 else \
                100.0 - (total - min_total) / span * 60.0
            # 合成质量分
            quality = (f.score + h.score) / 2.0
            utility = cost_score * price_weight + quality * score_weight

            # §28: 当最优组合由"非最便宜机票"构成（受约束影响，独立贪心不可达）
            #      时，记录证据说明按总效用选优而非单项贪心
            if f.candidate_id != greedy_flight.candidate_id and \
               (best_so_far is None or total < best_so_far):
                notes.append(
                    f"总成本({total:.0f}) 优于此前最优，但 flight={f.candidate_id} "
                    f"非最便宜机票 — 按总效用选优（约束下独立贪心不可达）")
            if best_so_far is None or total < best_so_far:
                best_so_far = total

            bundles.append(BundleCandidate(
                bundle_id=new_id("bnd"),
                task_id=task_id,
                components={"flight": f.candidate_id, "hotel": h.candidate_id},
                cost={"flight": f.price, "hotel": h.price * h.nights,
                      "total": round(total, 2)},
                score=round(utility, 1),
                notes=[n for n in notes if n],
            ))

    bundles.sort(key=lambda b: b.score, reverse=True)
    return BundleResult(bundles=bundles, notes=notes)


def best_bundle(bundles: List[BundleCandidate]) -> Optional[BundleCandidate]:
    return bundles[0] if bundles else None


def _min_total(flights: List[BundleComponent], hotels: List[BundleComponent]) -> float:
    return min(f.price for f in flights) + min(h.price * h.nights for h in hotels)


def _max_total(flights: List[BundleComponent], hotels: List[BundleComponent]) -> float:
    return max(f.price for f in flights) + max(h.price * h.nights for h in hotels)
