"""Aviationstack 实时状态源测试 — 映射正确性 + 无 key 显式 AUTH_REQUIRED。

真实端点管线验证（有 UA_AVIATIONSTACK_KEY 时运行，无 key 跳过）：
用户本机已配置有效 key（实测 CA123 返回实时数据），导出后可跑通。
"""
from __future__ import annotations

import os

import pytest

from universal_agent.adapters.aviationstack import (
    AviationstackFlightStatusSkill,
    aviationstack_marketplace_manifest,
)

# Aviationstack /v1/flights 响应形状（按官方文档结构）
AVIATIONSTACK_SAMPLE = {
    "pagination": {"limit": 1, "offset": 0, "count": 1, "total": 6},
    "data": [
        {
            "flight_date": "2026-08-15",
            "flight_status": "scheduled",
            "departure": {
                "airport": "Beijing Capital International", "iata": "PEK",
                "icao": "ZBAA", "terminal": "3", "gate": "H", "delay": None,
                "scheduled": "2026-08-15T08:40:00+00:00",
                "estimated": "2026-08-15T08:40:00+00:00",
                "actual": None,
            },
            "arrival": {
                "airport": "Narita International", "iata": "NRT",
                "icao": "RJAA", "terminal": "1", "gate": None, "delay": None,
                "scheduled": "2026-08-15T13:15:00+00:00",
                "estimated": "2026-08-15T13:15:00+00:00",
                "actual": None,
            },
            "flight": {"number": "CA123", "iata": "CA123", "icao": "CCA123"},
        }
    ],
}


class _FakeHttp:
    def __init__(self, payload):
        self.payload = payload
        self.last_params = None

    def get_json(self, url, params=None, headers=None, timeout_ms=None):
        self.last_params = params
        return self.payload


class TestAviationstackMapping:
    def test_live_status_maps_fields(self):
        skill = AviationstackFlightStatusSkill(api_key="test",
                                               http=_FakeHttp(AVIATIONSTACK_SAMPLE))
        s = skill.live_status("CA123", "2026-08-15")
        assert s["found"] is True
        assert s["flight"] == "CA123"
        assert s["status"] == "scheduled"
        assert s["status_zh"] == "计划"
        assert s["departure"]["iata"] == "PEK"
        assert s["departure"]["terminal"] == "3"
        assert s["departure"]["gate"] == "H"
        assert s["arrival"]["iata"] == "NRT"

    def test_no_records_returns_found_false(self):
        skill = AviationstackFlightStatusSkill(
            api_key="test", http=_FakeHttp({"pagination": {}, "data": []}))
        s = skill.live_status("CA999", "")
        assert s["found"] is False
        assert "未找到" in s["message"]

    @pytest.mark.skipif("os.environ.get('UA_AVIATIONSTACK_KEY')",
                        reason="环境中已配置 key，跳过无 key 断言")
    def test_health_auth_required_without_key(self):
        skill = AviationstackFlightStatusSkill()
        assert skill.health_check()["status"] == "AUTH_REQUIRED"

    def test_fetch_refuses_listing(self):
        """运营数据源不产出 RawListing（显式拒绝，§33 不混淆）。"""
        from universal_agent.adapters.ctrip import SkillUnavailable
        from universal_agent.coordinator.query_planner import FlightQuery

        skill = AviationstackFlightStatusSkill(api_key="test",
                                               http=_FakeHttp(AVIATIONSTACK_SAMPLE))
        with pytest.raises(SkillUnavailable) as ei:
            skill.fetch(FlightQuery(origin="SHA", destination="NRT",
                                    depart_date="2026-08-15",
                                    return_date="2026-08-16", nights=1))
        assert "运营数据" in str(ei.value)

    def test_prepare_action_blocked_and_manifest(self):
        skill = AviationstackFlightStatusSkill(api_key="k")
        assert skill.prepare_action("x", {})["allowed"] is False
        assert aviationstack_marketplace_manifest().domains == ["flight"]

    def test_exact_flight_preferred_over_fuzzy_first(self):
        """免费档 flight_iata 模糊匹配：必须优先精确航班，不取 data[0]。"""
        fuzzy = {
            "pagination": {"total": 3},
            "data": [
                {**AVIATIONSTACK_SAMPLE["data"][0],
                 "flight": {"number": "SC123", "iata": "SC123", "icao": "CDG123"}},
                {**AVIATIONSTACK_SAMPLE["data"][0],
                 "flight": {"number": "CA123", "iata": "CA123", "icao": "CCA123"}},
            ],
        }
        skill = AviationstackFlightStatusSkill(api_key="test", http=_FakeHttp(fuzzy))
        s = skill.live_status("CA123", "2026-08-15")
        assert s["flight"] == "CA123"  # 精确匹配优先，非 SC123

    def test_unknown_status_label_passthrough(self):
        from universal_agent.adapters.aviationstack.adapter import _status_label_zh
        assert _status_label_zh("landed") == "已到达"
        assert _status_label_zh("some_weird_status") == "some_weird_status"


@pytest.mark.skipif("not os.environ.get('UA_AVIATIONSTACK_KEY')",
                    reason="UA_AVIATIONSTACK_KEY 未配置，跳过真实端点测试")
class TestAviationstackLive:
    """真实端点（本机已配置有效 key 时运行）。"""

    def test_real_endpoint_live_status(self):
        skill = AviationstackFlightStatusSkill()
        h = skill.health_check()
        assert h["status"] == "HEALTHY", h
        s = skill.live_status("CA123")
        assert s["available"] is True
        if s["found"]:
            assert s["departure"]["iata"] or s["arrival"]["iata"]
