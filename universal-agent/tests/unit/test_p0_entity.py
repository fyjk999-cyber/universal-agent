"""P0.7 回归测试：Flight Entity Resolution strong/weak + confidence。

规则：
- 航班号完整 → Strong Entity Key
- 航班号缺失 → Weak Match，禁止直接 merge
- resolution_confidence: MATCH / PROBABLE_MATCH / UNKNOWN / CONFLICT
- 仅 MATCH 才合并 Candidate
- 同日期同路线不同航班号 → CONFLICT（不合并）
"""
from __future__ import annotations

import pytest

from universal_agent.core.contracts import RawLeg, RawListing
from universal_agent.domains.flight import (
    ResolutionConfidence,
    entity_key,
    resolve,
    strong_entity_key,
)


def _seg(flight_no: str, dep_time: str = "14:30", airline: str = "NZ") -> dict:
    return {
        "airline": airline, "flight_no": flight_no,
        "dep_airport": "PVG", "arr_airport": "AKL",
        "dep_time": dep_time, "arr_time": "06:30",
        "dep_date": "2026-08-31", "arr_date": "2026-09-01", "duration_min": 660,
    }


def _listing(flight_no: str, dep_time: str = "14:30", airline: str = "NZ",
             listing_id: str = "l", marketplace: str = "ctrip") -> RawListing:
    seg = _seg(flight_no, dep_time, airline)
    return RawListing(
        listing_id=listing_id, source=marketplace, marketplace_id=marketplace,
        task_id="t1", origin_airport="PVG", dest_airport="ZQN",
        depart_date="2026-08-31", return_date="2026-09-07", nights=7,
        price_cny=4380.0,
        outbound=RawLeg(segments=[seg], total_min=810, stops=1, layovers=[120],
                        layover_airports=["AKL"]),
        inbound=RawLeg(segments=[seg], total_min=870, stops=1, layovers=[120]),
        luggage={},
    )


class TestStrongKey:
    def test_same_flight_same_strong_key(self):
        a = _listing("NZ288", listing_id="a")
        b = _listing("NZ288", listing_id="b", marketplace="fliggy")
        assert strong_entity_key(a) == strong_entity_key(b)

    def test_different_flight_conflict(self):
        """同日期同路线不同航班号 → CONFLICT，不合并。"""
        a = _listing("NZ288", listing_id="a")
        b = _listing("NZ300", listing_id="b", marketplace="fliggy")
        r = resolve(a, b)
        assert r.confidence == ResolutionConfidence.CONFLICT
        # 旧逻辑：key 因航班号不同而不同 → 不会错误合并（改进点：显式 CONFLICT）

    def test_same_flight_match(self):
        a = _listing("NZ288", listing_id="a")
        b = _listing("NZ288", listing_id="b", marketplace="fliggy")
        r = resolve(a, b)
        assert r.confidence == ResolutionConfidence.MATCH
        assert r.strong is True

    def test_different_time_unknown(self):
        """同航班号不同时间 → 非同一实体（UNKNOWN/不合并）。"""
        a = _listing("NZ288", dep_time="14:30", listing_id="a")
        b = _listing("NZ288", dep_time="18:00", listing_id="b")
        r = resolve(a, b)
        assert r.confidence != ResolutionConfidence.MATCH


class TestWeakKey:
    def _no_flightno(self, listing_id: str = "w") -> RawListing:
        seg = _seg("", "14:30")  # flight_no 缺失
        return RawListing(
            listing_id=listing_id, source="s", marketplace_id="s", task_id="t1",
            origin_airport="PVG", dest_airport="ZQN",
            depart_date="2026-08-31", return_date="2026-09-07", nights=7,
            price_cny=4000.0,
            outbound=RawLeg(segments=[seg], total_min=810, stops=1),
            inbound=RawLeg(segments=[seg], total_min=870, stops=1),
            luggage={},
        )

    def test_missing_flight_no_weak_key(self):
        w = self._no_flightno()
        assert strong_entity_key(w) is None  # 无 strong key
        # weak key 只是 date|origin|dest
        assert entity_key(w).startswith("2026-08-31|PVG|ZQN")

    def test_weak_keys_equal_probable_match_not_merged(self):
        """P0.7 核心：同弱键 → PROBABLE_MATCH，禁止直接 merge。"""
        w1 = self._no_flightno("w1")
        w2 = self._no_flightno("w2")
        r = resolve(w1, w2)
        assert r.confidence == ResolutionConfidence.PROBABLE_MATCH
        assert r.strong is False  # 不 merge

    def test_weak_vs_strong_no_merge(self):
        """完整数据 vs 不完整数据（同路线）→ 不因弱键直接 merge。"""
        strong = _listing("NZ288", listing_id="s")
        weak = self._no_flightno("w")
        r = resolve(strong, weak)
        assert r.confidence != ResolutionConfidence.MATCH
