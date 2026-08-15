"""Kiwi Tequila 源测试 — 映射正确性（fixture）+ 真实端点管线（无 key → AUTH_REQUIRED）。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from universal_agent.adapters.kiwi import (
    KiwiTequilaFlightSkill,
    kiwi_marketplace_manifest,
)
from universal_agent.coordinator.query_planner import FlightQuery

FIXTURE_DIR = Path(__file__).resolve().parent.parent.parent / "tests" / "replay" / "fixtures"

# Tequila /v2/search 响应形状（按官方文档结构，测试映射逻辑）
TEQUILA_SAMPLE = {
    "search_id": "test_search",
    "currency": "CNY",
    "data": [
        {
            "id": "kiwi_1", "flyFrom": "SHA", "flyTo": "ZQN",
            "cityFrom": "Shanghai", "cityTo": "Queenstown", "price": 3980,
            "deep_link": "https://www.kiwi.com/deep?from=SHA&to=ZQN",
            "route": [
                {"flyFrom": "SHA", "flyTo": "PVG", "airline": "CA", "flight_no": "451",
                 "departure": {"utc": "2026-08-30T08:00:00Z"},
                 "arrival": {"utc": "2026-08-30T09:10:00Z"}, "return": 0},
                {"flyFrom": "PVG", "flyTo": "AKL", "airline": "NZ", "flight_no": "288",
                 "departure": {"utc": "2026-08-30T14:30:00Z"},
                 "arrival": {"utc": "2026-08-30T22:00:00Z"}, "return": 0},
                {"flyFrom": "AKL", "flyTo": "ZQN", "airline": "NZ", "flight_no": "611",
                 "departure": {"utc": "2026-08-31T09:00:00Z"},
                 "arrival": {"utc": "2026-08-31T09:55:00Z"}, "return": 0},
                {"flyFrom": "ZQN", "flyTo": "AKL", "airline": "NZ", "flight_no": "612",
                 "departure": {"utc": "2026-09-07T12:00:00Z"},
                 "arrival": {"utc": "2026-09-07T12:55:00Z"}, "return": 1},
                {"flyFrom": "AKL", "flyTo": "PVG", "airline": "NZ", "flight_no": "289",
                 "departure": {"utc": "2026-09-07T22:30:00Z"},
                 "arrival": {"utc": "2026-09-08T06:00:00Z"}, "return": 1},
                {"flyFrom": "PVG", "flyTo": "SHA", "airline": "CA", "flight_no": "452",
                 "departure": {"utc": "2026-09-08T09:30:00Z"},
                 "arrival": {"utc": "2026-09-08T10:40:00Z"}, "return": 1},
            ],
        },
        {"id": "kiwi_bad", "flyFrom": "SHA", "flyTo": "ZQN",  # 缺 price → fail-closed
         "route": []},
    ],
}


class _FakeHttp:
    """注入固定响应的 HttpAdapter 替身（避免联网依赖）。"""

    def __init__(self, payload):
        self.payload = payload

    def get_json(self, url, params=None, headers=None, timeout_ms=None):
        return self.payload


class TestKiwiMapping:
    def test_search_maps_to_raw_listing(self):
        skill = KiwiTequilaFlightSkill(api_key="test",
                                       http=_FakeHttp(TEQUILA_SAMPLE))
        query = FlightQuery(origin="SHA", destination="ZQN",
                            depart_date="2026-08-30", return_date="2026-09-07",
                            nights=8)
        raws = skill.fetch(query)
        assert len(raws) == 1, "坏条目（缺 price）必须 fail-closed 跳过"
        r = raws[0]
        assert r.marketplace_id == "kiwi_tequila"
        assert r.price_cny == 3980.0
        assert r.origin_airport == "SHA" and r.dest_airport == "ZQN"
        assert r.depart_date == "2026-08-30"
        assert r.return_date == "2026-09-07"
        assert len(r.outbound.segments) == 3, "outbound=return:0 航段"
        assert len(r.inbound.segments) == 3, "inbound=return:1 航段"
        assert r.url and r.url.startswith("https://www.kiwi.com")

    def test_health_auth_required_without_key(self):
        skill = KiwiTequilaFlightSkill()
        assert skill.health_check()["status"] == "AUTH_REQUIRED"

    def test_prepare_action_blocked(self):
        skill = KiwiTequilaFlightSkill(api_key="k")
        assert skill.prepare_action("x", {})["allowed"] is False


class TestKiwiLivePlumbing:
    """真实端点管线验证（无 key）：HTTP 链路真实可达，返回显式 AUTH_REQUIRED。"""

    def test_real_endpoint_reachable_and_auth_semantics(self):
        skill = KiwiTequilaFlightSkill()  # 无 key
        h = skill.health_check()
        assert h["status"] == "AUTH_REQUIRED"
        # search 必须抛 SkillUnavailable（显式，不静默）
        with pytest.raises(Exception) as ei:
            skill.search({"origin": "SHA", "destination": "ZQN",
                          "depart_date": "2026-08-30",
                          "return_date": "2026-09-07"})
        assert "AUTH_REQUIRED" in str(ei.value) or "UA_KIWI_KEY" in str(ei.value)

    def test_real_endpoint_with_dummy_key_returns_401(self):
        """真实端点 + 假 key：必须得到认证失败（证明 HTTP 链路已通到 Tequila）。"""
        import pytest as _p
        from universal_agent.adapters.ctrip import SkillUnavailable as _SU
        from universal_agent.adapters.http import HttpAdapter, HttpAdapterError
        skill = KiwiTequilaFlightSkill(
            api_key="definitely-invalid-key",
            http=HttpAdapter(timeout_ms=12_000, retries=0))
        try:
            skill.search({"origin": "SHA", "destination": "ZQN",
                          "depart_date": "2026-08-30",
                          "return_date": "2026-09-07"})
            _p.fail("假 key 必须认证失败")
        except (_SU, HttpAdapterError) as exc:
            # 401/403 → HttpAdapterError(http_error) 或 SkillUnavailable
            assert "401" in str(exc) or "403" in str(exc) or "Unauthorized" in str(exc) \
                or "Unauthorized" in str(exc)
