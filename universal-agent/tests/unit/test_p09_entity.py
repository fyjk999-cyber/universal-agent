"""P0.9-2 回归测试：Empty Segments Entity Resolution。

规则：
- 空 segments（outbound+inbound 均空）→ 绝不 Strong
- round-trip 缺任一方向（只有 outbound 或只有 inbound）→ 不 Strong
- 缺 flight_no / dep_time → 不 Strong
- 完整双方向 round-trip → Strong
"""
from __future__ import annotations

from universal_agent.core.contracts import RawLeg, RawListing
from universal_agent.domains.flight import strong_entity_key


def _seg(flight_no="NZ288", dep_time="14:30", dep_date="2026-08-31",
         arr_date="2026-09-01") -> dict:
    return {
        "airline": "NZ", "flight_no": flight_no,
        "dep_airport": "PVG", "arr_airport": "AKL",
        "dep_time": dep_time, "arr_time": "06:30",
        "dep_date": dep_date, "arr_date": arr_date, "duration_min": 660,
    }


def _listing(outbound=None, inbound=None) -> RawListing:
    return RawListing(
        listing_id="l", source="s", marketplace_id="s", task_id="t1",
        origin_airport="PVG", dest_airport="ZQN",
        depart_date="2026-08-31", return_date="2026-09-07", nights=7,
        price_cny=4380.0,
        outbound=outbound or RawLeg(segments=[]),
        inbound=inbound or RawLeg(segments=[]),
        luggage={},
    )


class TestEmptySegments:
    def test_empty_segments_never_strong(self):
        """空 segments → 绝不 Strong。"""
        l = _listing()
        assert strong_entity_key(l) is None

    def test_outbound_only_never_strong_for_roundtrip(self):
        """只有 outbound → 不 Strong（round-trip 缺返程）。"""
        l = _listing(outbound=RawLeg(segments=[_seg()], total_min=810, stops=1))
        assert strong_entity_key(l) is None

    def test_inbound_only_never_strong_for_roundtrip(self):
        """只有 inbound → 不 Strong。"""
        l = _listing(inbound=RawLeg(segments=[_seg()], total_min=870, stops=1))
        assert strong_entity_key(l) is None

    def test_missing_flight_number_never_strong(self):
        l = _listing(
            outbound=RawLeg(segments=[_seg(flight_no="")], total_min=810, stops=1),
            inbound=RawLeg(segments=[_seg(flight_no="")], total_min=870, stops=1))
        assert strong_entity_key(l) is None

    def test_missing_departure_time_never_strong(self):
        l = _listing(
            outbound=RawLeg(segments=[_seg(dep_time="")], total_min=810, stops=1),
            inbound=RawLeg(segments=[_seg(dep_time="")], total_min=870, stops=1))
        assert strong_entity_key(l) is None

    def test_missing_date_fields_never_strong(self):
        l = _listing(
            outbound=RawLeg(segments=[_seg(dep_date="")], total_min=810, stops=1),
            inbound=RawLeg(segments=[_seg(dep_date="")], total_min=870, stops=1))
        assert strong_entity_key(l) is None

    def test_complete_roundtrip_generates_strong_key(self):
        l = _listing(
            outbound=RawLeg(segments=[_seg()], total_min=810, stops=1),
            inbound=RawLeg(segments=[_seg()], total_min=870, stops=1))
        assert strong_entity_key(l) is not None
