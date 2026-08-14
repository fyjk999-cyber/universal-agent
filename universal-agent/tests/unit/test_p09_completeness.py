"""P0.9-3 回归测试：Skyscanner DataCompleteness 修复。

规则：
- price-only → DISCOVERED/PARTIAL
- duration-only → PARTIAL（不是 STRUCTURED）
- 无 segments → 绝不 STRUCTURED
- 无 return detail → 绝不 STRUCTURED
- stops 未知 → -1（不伪造 0）
- 完整 listing 可 STRUCTURED（通过显式字段构造）
"""
from __future__ import annotations

from universal_agent.adapters.skyscanner import SkyscannerAdapter, SkyscannerConfig
from universal_agent.core.contracts import DataCompleteness, RawLeg, RawListing
from universal_agent.core.contracts.raw import field_completeness_score
from universal_agent.coordinator.query_planner import FlightQuery


def _q() -> FlightQuery:
    return FlightQuery(origin="PVG", destination="ZQN",
                       depart_date="2026-08-31", return_date="2026-09-07", nights=7)


class TestSkyscannerCompleteness:
    def test_build_listing_always_partial(self):
        """search 解析无完整 segments → 恒 PARTIAL。"""
        adapter = SkyscannerAdapter(config=SkyscannerConfig(request_delay_sec=0))
        listing = adapter._build_listing(_q(), 4380, 0)
        assert listing.extra["completeness"] == DataCompleteness.PARTIAL.value

    def test_duration_only_is_partial_not_structured(self):
        """即使有 duration，仍是 PARTIAL（非 STRUCTURED）。"""
        adapter = SkyscannerAdapter(config=SkyscannerConfig(request_delay_sec=0))
        listing = adapter._build_listing(_q(), 4380, 935)
        assert listing.extra["completeness"] == DataCompleteness.PARTIAL.value
        assert listing.extra["completeness"] != DataCompleteness.STRUCTURED.value

    def test_stops_unknown_not_zero(self):
        """stops 未知 → -1，不伪造 0。"""
        adapter = SkyscannerAdapter(config=SkyscannerConfig(request_delay_sec=0))
        listing = adapter._build_listing(_q(), 4380, 935)
        assert listing.outbound.stops == -1
        assert listing.inbound.stops == -1

    def test_without_segments_never_structured(self):
        listing = RawListing(
            listing_id="x", source="s", marketplace_id="s", task_id="t1",
            origin_airport="PVG", dest_airport="ZQN",
            depart_date="2026-08-31", return_date="2026-09-07", nights=7,
            price_cny=4380.0,
            outbound=RawLeg(segments=[], total_min=935, stops=-1),
            inbound=RawLeg(segments=[], total_min=0, stops=-1),
            luggage={},
            extra={"completeness": DataCompleteness.PARTIAL.value})
        assert listing.extra["completeness"] == DataCompleteness.PARTIAL.value
        assert field_completeness_score(listing) < 0.5

    def test_complete_listing_can_be_structured(self):
        """完整 segments（双方向）→ 可 STRUCTURED（detail 验证后）。"""
        seg = {"airline": "NZ", "flight_no": "NZ288", "dep_airport": "PVG",
               "arr_airport": "AKL", "dep_time": "14:30", "arr_time": "06:30",
               "dep_date": "2026-08-31", "arr_date": "2026-09-01", "duration_min": 660}
        listing = RawListing(
            listing_id="c", source="s", marketplace_id="s", task_id="t1",
            origin_airport="PVG", dest_airport="ZQN",
            depart_date="2026-08-31", return_date="2026-09-07", nights=7,
            price_cny=4380.0,
            outbound=RawLeg(segments=[seg], total_min=810, stops=1, layovers=[120]),
            inbound=RawLeg(segments=[seg], total_min=870, stops=1, layovers=[120]),
            luggage={},
            extra={"completeness": DataCompleteness.STRUCTURED.value})
        assert listing.extra["completeness"] == DataCompleteness.STRUCTURED.value
        assert field_completeness_score(listing) > 0.5
