"""Bundle Optimizer tests (§27, §28) — TOTAL TRIP UTILITY, non-greedy."""
from __future__ import annotations

from universal_agent.core.bundling import (
    BundleComponent,
    best_bundle,
    build_bundles,
)


def _flight(cid: str, price: float, score: float = 80.0) -> BundleComponent:
    return BundleComponent(candidate_id=cid, domain="flight", price=price, score=score)


def _hotel(cid: str, price_per_night: float, nights: int = 7,
           score: float = 75.0) -> BundleComponent:
    return BundleComponent(candidate_id=cid, domain="hotel",
                           price=price_per_night, score=score, nights=nights)


class TestBundleOptimizer:
    def test_flight_only_bundles(self):
        flights = [_flight("f1", 4000), _flight("f2", 5000)]
        res = build_bundles(flights, hotels=None, task_id="t1")
        assert len(res.bundles) == 2
        assert best_bundle(res.bundles).components == {"flight": "f1"}

    def test_combines_flight_and_hotel(self):
        flights = [_flight("f1", 4000)]
        hotels = [_hotel("h1", 1000)]
        res = build_bundles(flights, hotels, task_id="t1")
        b = res.bundles[0]
        assert b.components == {"flight": "f1", "hotel": "h1"}
        assert b.cost["total"] == 4000 + 1000 * 7
        assert b.cost["hotel"] == 7000

    def test_non_greedy_total_utility_wins(self):
        """§28 核心：约束下（航班日期绑定酒店），独立贪心会选错。

        场景：flightA 最便宜但只能配贵酒店（约束），flightB 贵¥300 可配便宜酒店。
        独立贪心 = flightA(最低) + hotelCheap(最低) → 非法组合；
        正确结果 = flightB + hotelCheap（总效用最优）。
        """
        flights = [
            _flight("flightA", 4200),  # 最便宜机票
            _flight("flightB", 4500),  # 贵 ¥300
        ]
        hotels = [
            _hotel("hotelExpensive", 1400),
            _hotel("hotelCheap", 1250),  # 最便宜酒店
        ]

        def valid_pair(f, h):
            # 约束：flightA 只能配 hotelExpensive（模拟日期/区域绑定）
            if f.candidate_id == "flightA":
                return h.candidate_id == "hotelExpensive"
            return True

        res = build_bundles(flights, hotels, task_id="t1", valid_pair=valid_pair)
        best = best_bundle(res.bundles)
        # 独立贪心（flightA + hotelCheap）非法被排除；最优为 flightB + hotelCheap
        assert best.components["flight"] == "flightB"
        assert best.components["hotel"] == "hotelCheap"
        # 合法组合：A+Expensive=14000, B+Cheap=13250 → B+Cheap 总成本更低
        totals = {tuple(b.components.values()): b.cost["total"] for b in res.bundles}
        assert totals[("flightB", "hotelCheap")] < totals[("flightA", "hotelExpensive")]

    def test_note_recorded_for_non_min_flight_winning_bundle(self):
        flights = [_flight("flightA", 4200), _flight("flightB", 4500)]
        hotels = [_hotel("hotelExpensive", 1400), _hotel("hotelCheap", 1250)]

        def valid_pair(f, h):
            return not (f.candidate_id == "flightA" and h.candidate_id == "hotelCheap")

        res = build_bundles(flights, hotels, task_id="t1", valid_pair=valid_pair)
        best = best_bundle(res.bundles)
        assert best.components["flight"] == "flightB"
        assert any("总成本" in n and "非最便宜机票" in n for n in best.notes)

    def test_sorted_by_utility_desc(self):
        flights = [_flight("f1", 3000), _flight("f2", 6000)]
        hotels = [_hotel("h1", 500), _hotel("h2", 2000)]
        res = build_bundles(flights, hotels, task_id="t1")
        scores = [b.score for b in res.bundles]
        assert scores == sorted(scores, reverse=True)
