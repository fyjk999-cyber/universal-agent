"""看板 Flight 端点测试 — 中文输入、机场 datalist、官方会话桥状态（无网络依赖）。

策略：启动临时 ThreadingHTTPServer（端口 0），请求：
- /api/flight/airports → 别名列表（含 上海→PVG）
- /api/flight（无 UA_KIWI_KEY）→ 显式 AUTH_REQUIRED，listings 空，不伪造
- /api/browser → 白名单桥状态
- /api/sources → 含 aviationstack 状态（无 key → AUTH_REQUIRED）
"""
from __future__ import annotations

import json
import threading
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from universal_agent.apps.dashboard import Handler


@pytest.fixture(scope="module")
def dash_url():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


def _get(url: str, params: dict | None = None) -> dict:
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


class TestDashboardFlight:
    def test_airports_endpoint(self, dash_url):
        d = _get(f"{dash_url}/api/flight/airports", {"q": "上海"})
        assert d["total"] >= 1
        assert any(a["alias"] == "上海" and a["iata"] == "PVG"
                   for a in d["airports"])

    def test_airports_empty_query_returns_all(self, dash_url):
        d = _get(f"{dash_url}/api/flight/airports")
        assert d["total"] > 20

    def test_flight_endpoint_no_key_auth_required(self, dash_url):
        """无 UA_KIWI_KEY：显式 AUTH_REQUIRED，listings 空（不伪造数据）。"""
        d = _get(f"{dash_url}/api/flight",
                 {"from": "上海", "to": "东京", "date": "2026-08-30"})
        assert d["source_health"]["status"] == "AUTH_REQUIRED"
        assert d["listings"] == []

    def test_browser_bridge_endpoint(self, dash_url):
        d = _get(f"{dash_url}/api/browser")
        assert d["bridge"]["allowed_host_count"] > 10
        assert "www.airchina.com.cn" in d["allowed_hosts"]

    def test_sources_endpoint_includes_aviationstack(self, dash_url):
        d = _get(f"{dash_url}/api/sources")
        assert "aviationstack" in d["sources"]
        # 无 key 环境必须显式 AUTH_REQUIRED，不得冒充 HEALTHY
        import os as _os
        if not _os.environ.get("UA_AVIATIONSTACK_KEY"):
            assert d["sources"]["aviationstack"]["status"] == "AUTH_REQUIRED"


class TestResolveAirportViaSkill:
    def test_resolve_airport_static(self):
        from universal_agent.adapters.aviationstack import (
            AviationstackFlightStatusSkill)
        assert AviationstackFlightStatusSkill.resolve_airport("北京") == "PEK"
        assert AviationstackFlightStatusSkill.resolve_airport("hgh") == "HGH"
        assert AviationstackFlightStatusSkill.resolve_airport("火星") is None
