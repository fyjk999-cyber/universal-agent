"""P0.6 回归测试：Skyscanner 不完整数据 Fail Closed。

规则：缺少 flight number/segments/stops/duration 的数据
- 禁止默认 stops=0
- 禁止获得直飞加分/短时长加分
- 标记 DataCompleteness（PARTIAL）
- PARTIAL 数据禁止 FINAL TOP5（在 shadow scan 评分中体现）
"""
from __future__ import annotations

import pytest

from universal_agent.core.contracts import DataCompleteness, RawLeg, RawListing
from universal_agent.core.contracts.raw import field_completeness_score
from universal_agent.domains.flight.scoring import score_listing, stops_score


def _incomplete_listing() -> RawListing:
    """Skyscanner 解析出的不完整数据：无 segments，stops=-1。"""
    return RawListing(
        listing_id="sky-incomplete", source="skyscanner", marketplace_id="skyscanner",
        task_id="t1", origin_airport="PVG", dest_airport="ZQN",
        depart_date="2026-08-31", return_date="2026-09-07", nights=7,
        price_cny=3980.0,
        outbound=RawLeg(segments=[], total_min=0, stops=-1),
        inbound=RawLeg(segments=[], total_min=0, stops=-1),
        luggage={}, extra={"completeness": DataCompleteness.PARTIAL.value},
    )


def _complete_listing() -> RawListing:
    seg = {
        "airline": "NZ", "flight_no": "NZ288", "dep_airport": "PVG",
        "arr_airport": "AKL", "dep_time": "14:30", "arr_time": "06:30",
        "dep_date": "2026-08-31", "arr_date": "2026-09-01", "duration_min": 660,
    }
    return RawListing(
        listing_id="sky-complete", source="skyscanner", marketplace_id="skyscanner",
        task_id="t1", origin_airport="PVG", dest_airport="ZQN",
        depart_date="2026-08-31", return_date="2026-09-07", nights=7,
        price_cny=4380.0,
        outbound=RawLeg(segments=[seg], total_min=810, stops=1, layovers=[120],
                        layover_airports=["AKL"]),
        inbound=RawLeg(segments=[seg], total_min=870, stops=0, layovers=[120]),
        luggage={},
    )


class TestFailClosed:
    def test_incomplete_no_direct_bonus(self):
        """stops=-1 → 不获得直飞 100 分。"""
        inc = _incomplete_listing()
        assert inc.outbound.stops == -1
        assert stops_score(inc) == 50.0  # 中性分，非直飞 100

    def test_incomplete_not_ranked_as_top(self):
        """不完整数据分数低于完整数据（禁进 Final Top5 顶部）。"""
        inc = _incomplete_listing()
        comp = _complete_listing()
        s_inc = score_listing(inc, market_min=3980)
        s_comp = score_listing(comp, market_min=3980)
        # 价格更便宜的不完整数据也不得超过完整数据结构分
        assert s_inc["total"] < s_comp["total"]

    def test_completeness_tagged(self):
        inc = _incomplete_listing()
        assert inc.extra["completeness"] == DataCompleteness.PARTIAL.value
        comp = _complete_listing()
        # 完整数据 completeness 由构造方标注；score 应体现
        assert field_completeness_score(inc) < field_completeness_score(comp)

    def test_field_completeness_score(self):
        inc = _incomplete_listing()
        comp = _complete_listing()
        assert 0.0 <= field_completeness_score(inc) <= 1.0
        assert field_completeness_score(inc) < field_completeness_score(comp)

    def test_complete_data_scores_normally(self):
        comp = _complete_listing()
        assert stops_score(comp) == 60.0  # 1 stop → 60
