"""Flight Airport & Airline 知识层测试（借自本地机票 OS 数据，2026-07 整理）。

验证：中文城市→IATA 解析、航司名录查询、fail-closed（不猜测）。
"""
from __future__ import annotations

import pytest

from universal_agent.domains.flight.airports import (
    AIRLINE_CATALOG,
    airline_booking_url,
    airline_info,
    airline_name_zh,
    airport_name_zh,
    official_airline_hosts,
    resolve_airport,
)


class TestResolveAirport:
    def test_chinese_city_to_iata(self):
        assert resolve_airport("上海") == "PVG"
        assert resolve_airport("北京") == "PEK"
        assert resolve_airport("东京") == "NRT"

    def test_airport_name_to_iata(self):
        assert resolve_airport("杭州萧山") == "HGH"
        assert resolve_airport("首都机场") == "PEK"
        assert resolve_airport("浦东机场") == "PVG"

    def test_iata_passthrough_case_insensitive(self):
        assert resolve_airport("hgh") == "HGH"
        assert resolve_airport("PVG") == "PVG"

    def test_whitespace_and_parens_tolerant(self):
        assert resolve_airport(" 上海 ") == "PVG"
        assert resolve_airport("北京（首都）") == "PEK"

    def test_unknown_returns_none(self):
        assert resolve_airport("火星") is None
        assert resolve_airport("") is None
        assert resolve_airport(None) is None

    def test_airport_name_zh(self):
        assert airport_name_zh("PVG") == "上海浦东国际机场"
        assert airport_name_zh("XXX") is None


class TestAirlineCatalog:
    def test_catalog_has_major_carriers(self):
        for iata in ("CA", "MU", "CZ", "HU", "9C"):
            assert iata in AIRLINE_CATALOG, f"航司名录缺 {iata}"

    def test_airline_info(self):
        info = airline_info("CA")
        assert info["name_zh"] == "中国国际航空"
        assert info["booking_url"].startswith("https://")

    def test_airline_name_zh_fallback(self):
        assert airline_name_zh("CA") == "中国国际航空"
        assert airline_name_zh("ZZ") == "ZZ"  # 未收录返回原码，不伪造
        assert airline_name_zh(None) == "?"

    def test_booking_url_none_for_unknown(self):
        assert airline_booking_url("ZZ") is None

    def test_official_hosts_all_https_hostnames(self):
        hosts = official_airline_hosts()
        assert "www.airchina.com.cn" in hosts
        assert "www.csair.com" in hosts
        for h in hosts:
            assert "." in h and " " not in h


class TestKiwiResolution:
    """Kiwi adapter 中文输入解析（fail-closed）。"""

    def test_kiwi_search_accepts_chinese_city(self):
        from universal_agent.adapters.kiwi import KiwiTequilaFlightSkill

        class _FakeHttp:
            def get_json(self, url, params=None, headers=None, timeout_ms=None):
                assert params["fly_from"] == "PVG"  # 上海 → 浦东
                assert params["fly_to"] == "NRT"
                return {"data": []}

        skill = KiwiTequilaFlightSkill(api_key="test", http=_FakeHttp())
        assert skill.search({"origin": "上海", "destination": "东京",
                             "depart_date": "2026-08-30"}) == []

    def test_kiwi_search_unknown_city_fail_closed(self):
        from universal_agent.adapters.kiwi import KiwiTequilaFlightSkill
        from universal_agent.adapters.ctrip import SkillUnavailable

        class _FakeHttp:
            def get_json(self, url, params=None, headers=None, timeout_ms=None):
                raise AssertionError("不应发起网络请求")

        skill = KiwiTequilaFlightSkill(api_key="test", http=_FakeHttp())
        with pytest.raises(SkillUnavailable) as ei:
            skill.search({"origin": "火星", "destination": "东京",
                          "depart_date": "2026-08-30"})
        assert "无法识别" in str(ei.value)
