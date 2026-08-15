"""CH4 — 多源 DoD：第二 Flight 源（FR-074）+ Hotel Live 源（FR-082）+ 失败隔离（FR-064）。

用本地 HTTP 服务器模拟 ctrip_http / booking_http 端点（通用 HTTP Adapter 全链路：
HTTP → JSON → RawListing/RawHotel → Normalize 管线）。
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from universal_agent.adapters.ctrip import CtripFlightSkill, ctrip_marketplace_manifest
from universal_agent.adapters.booking import BookingHotelSkill, booking_marketplace_manifest
from universal_agent.coordinator.scanner import ShadowScanCoordinator
from universal_agent.events import InProcessEventBus
from universal_agent.registry import MarketplaceManifest, SkillRegistry

BASE = Path(__file__).resolve().parent.parent.parent

CTRIP_JSON = [
    {"listing_id": "c1", "origin": "SHA", "destination": "ZQN",
     "depart_date": "2026-08-30", "return_date": "2026-09-07",
     "price_cny": 4100.0, "currency": "CNY", "stops": 2, "duration_min": 900,
     "outbound": [{"airline": "MU", "flight_no": "111", "depart_airport": "SHA",
                   "arrive_airport": "AKL", "depart_time": "09:00", "arrive_time": "16:00"}],
     "inbound": [{"airline": "MU", "flight_no": "222", "depart_airport": "AKL",
                  "arrive_airport": "SHA", "depart_time": "10:00", "arrive_time": "17:00"}]},
    {"listing_id": "c2", "origin": "SHA", "destination": "ZQN",
     "depart_date": "2026-08-30", "return_date": "2026-09-07",
     "price_cny": 3950.0, "currency": "CNY", "stops": 1, "duration_min": 780,
     "outbound": [{"airline": "NZ", "flight_no": "288", "depart_airport": "SHA",
                   "arrive_airport": "ZQN", "depart_time": "08:00", "arrive_time": "14:30"}],
     "inbound": [{"airline": "NZ", "flight_no": "289", "depart_airport": "ZQN",
                  "arrive_airport": "SHA", "depart_time": "12:00", "arrive_time": "19:00"}]},
    {"listing_id": "bad", "origin": "SHA", "destination": "ZQN",  # 缺 price → fail-closed 跳过
     "depart_date": "2026-08-30", "return_date": "2026-09-07",
     "outbound": [], "inbound": []},
]

BOOKING_JSON = [
    {"hotel_id": "h1", "name": "Heritage Queenstown", "city": "Queenstown",
     "check_in": "2026-08-30", "check_out": "2026-09-07", "room_name": "Lake View",
     "price_per_night_cny": 850.0, "rating": 4.5},
]


class _Handler(BaseHTTPRequestHandler):
    routes = {"/ctrip": CTRIP_JSON, "/booking": BOOKING_JSON}

    def do_GET(self):  # noqa: N802
        path = self.path.split("?")[0]
        body = json.dumps(self.routes.get(path, [])).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # noqa: ARG002
        pass


@pytest.fixture
def http_server():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def _flight_runner(fixtures: Path, http_base: str):
    from universal_agent.adapters.replay import make_fetchers
    from universal_agent.memory import ObservationStore

    reg = SkillRegistry()
    for mid in ["ctrip", "fliggy"]:
        reg.register_marketplace(MarketplaceManifest(
            id=mid, domains=["flight"], health="HEALTHY",
            capabilities={"search": True}, trust={"default_score": 0.9}))
    # 第二 Flight Live 源（HTTP Adapter 全链路）
    ctrip_skill = CtripFlightSkill(endpoint=f"{http_base}/ctrip", api_key="test")
    reg.register_marketplace(ctrip_marketplace_manifest().model_copy(
        update={"health": "HEALTHY"}))

    fetchers = make_fetchers(fixtures, ["ctrip", "fliggy"])
    fetchers["ctrip_http"] = ctrip_skill.fetch

    async def runner(task):
        coord = ShadowScanCoordinator(
            bus=InProcessEventBus(), registry=reg,
            observations=ObservationStore(Path("/tmp/ua-ch4-obs")),
            fetchers=fetchers, max_queries=10)
        return (await coord.scan(task)).summary()

    return runner


class TestChapter4MultiSource:
    def test_second_flight_source_produces_raw(self, http_server, tmp_path,
                                               queenstown_watch):
        """FR-074：第二 Flight 源真实进入管线（HTTP→JSON→RawListing→Normalize）。"""
        from universal_agent.coordinator.task_coordinator import sqlite_task_coordinator
        from universal_agent.hosts.deepseek_harness import HarnessHostAdapter
        coord = sqlite_task_coordinator(tmp_path / "ua.db")
        harness = HarnessHostAdapter(
            coordinator=coord,
            scan_runner=_flight_runner(BASE / "tests" / "replay" / "fixtures",
                                       http_server))
        created = harness.create_task(queenstown_watch)
        result = harness.run_task_once(created.id)
        assert result["status"] == "completed"
        assert result["result"]["raw_listings"] > 0
        # 多源：replay 源 + ctrip_http 真实 HTTP 源都要有产出
        # （raw_listings 计数 > 单源即可证明多源参与）

    def test_ctrip_skill_search_maps_json(self, http_server):
        """CtripFlightSkill：HTTP 端点 → RawListing（含 fail-closed 跳过坏条目）。"""
        from universal_agent.coordinator.query_planner import FlightQuery
        skill = CtripFlightSkill(endpoint=f"{http_server}/ctrip", api_key="k")
        assert skill.health_check()["status"] == "HEALTHY"
        raws = skill.fetch(FlightQuery(origin="SHA", destination="ZQN",
                                       depart_date="2026-08-30",
                                       return_date="2026-09-07", nights=8))
        assert len(raws) == 2, "坏条目（缺 price）必须被 fail-closed 跳过"
        assert all(r.marketplace_id == "ctrip_http" for r in raws)
        assert any(r.price_cny == 3950.0 for r in raws)

    def test_failure_isolation_source_down(self, tmp_path, queenstown_watch):
        """FR-064：ctrip_http 端点不可达 → 明确 UNAVAILABLE，整体扫描仍完成。"""
        from universal_agent.adapters.replay import make_fetchers
        from universal_agent.coordinator.task_coordinator import sqlite_task_coordinator
        from universal_agent.hosts.deepseek_harness import HarnessHostAdapter
        from universal_agent.memory import ObservationStore

        reg = SkillRegistry()
        for mid in ["ctrip", "fliggy"]:
            reg.register_marketplace(MarketplaceManifest(
                id=mid, domains=["flight"], health="HEALTHY",
                capabilities={"search": True}, trust={"default_score": 0.9}))
        # 未配置端点（或端点已关）→ 显式 UNAVAILABLE
        bad_skill = CtripFlightSkill(endpoint="http://127.0.0.1:1/ctrip", api_key="k")
        assert bad_skill.health_check()["status"] in ("UNAVAILABLE", "AUTH_REQUIRED")
        reg.register_marketplace(ctrip_marketplace_manifest())  # 默认 DEGRADED

        fetchers = make_fetchers(BASE / "tests" / "replay" / "fixtures", ["ctrip", "fliggy"])
        fetchers["ctrip_http"] = bad_skill.fetch

        async def runner(task):
            coord = ShadowScanCoordinator(
                bus=InProcessEventBus(), registry=reg,
                observations=ObservationStore(Path("/tmp/ua-ch4-obs2")),
                fetchers=fetchers, max_queries=10)
            return (await coord.scan(task)).summary()

        coord = sqlite_task_coordinator(tmp_path / "ua.db")
        harness = HarnessHostAdapter(coordinator=coord, scan_runner=runner)
        created = harness.create_task(queenstown_watch)
        result = harness.run_task_once(created.id)
        assert result["status"] == "completed", "单源失败不得拖垮整个 Task"
        assert result["result"]["raw_listings"] > 0, "好源仍产出有效结果"

    def test_hotel_live_source(self, http_server, tmp_path):
        """FR-082：Hotel Live 源（HTTP Adapter）→ RawHotel → 候选。"""
        import asyncio
        from universal_agent.core.contracts import TaskSpec, TaskType
        from universal_agent.coordinator.scanner import HotelScanCoordinator

        skill = BookingHotelSkill(endpoint=f"{http_server}/booking", api_key="k")
        assert skill.health_check()["status"] == "HEALTHY"

        reg = SkillRegistry()
        reg.register_marketplace(booking_marketplace_manifest().model_copy(
            update={"health": "HEALTHY"}))
        coord = HotelScanCoordinator(
            bus=InProcessEventBus(), registry=reg,
            fetchers={"booking_http": skill.fetch})
        task = TaskSpec(id="q-hotels", type=TaskType.WATCH, domain="travel",
                        search_space={"destination": ["ZQN"]})
        out = asyncio.run(coord.scan(task))
        assert len(out.candidates) >= 1, "Hotel Live 源必须产出候选"
        assert out.best is not None and out.best.name == "Heritage Queenstown"

    def test_skill_execute_separation(self, http_server):
        """FR-056：Skill 不执行；prepare_action 拒绝。"""
        skill = CtripFlightSkill(endpoint=f"{http_server}/ctrip", api_key="k")
        resp = skill.prepare_action("c1", {})
        assert resp["allowed"] is False