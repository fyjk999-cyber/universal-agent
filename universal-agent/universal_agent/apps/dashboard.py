"""Universal Agent Dashboard — 可视化看板（零依赖，Python 标准库）。

显示：
- 系统健康（DB/RepositorySet/Host）
- Railway 12306 真实数据全流程（raw → candidates → 排名 → 机会 → 通知）
- 数据源状态（12306 / Skyscanner / Kiwi / Ctrip / Booking）
- Pipeline 流转示意

用法：
  python -m universal_agent.apps.dashboard --port 8632
  # 打开 http://127.0.0.1:8632

API：
  GET /            → 看板页面
  GET /api/health  → 服务健康
  GET /api/railway → Railway 扫描结果（60s 缓存，避免 12306 限流）
  GET /api/sources → 数据源状态
"""
from __future__ import annotations

import argparse
import json
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict

log = logging.getLogger("ua.dashboard")

BASE = Path(__file__).resolve().parent.parent.parent
HTML_FILE = Path(__file__).resolve().parent / "dashboard.html"

CACHE_TTL = 60  # 秒；12306 查询间隔 >1s，避免限流
RAILWAY_QUERY = {"from_city": "上海", "to_city": "杭州东", "date": "2026-08-20"}


class ScanCache:
    """带 TTL 的扫描结果缓存（后台线程刷新，锁保护）。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._railway: Dict[str, Any] = {}
        self._railway_at: float = 0.0
        self._last_error: str = ""

    def railway(self, force: bool = False) -> Dict[str, Any]:
        now = time.time()
        with self._lock:
            if force or (now - self._railway_at) > CACHE_TTL:
                self._railway_at = now
            else:
                return self._railway
        # 在锁外执行扫描（网络调用不应持锁）
        try:
            result = self._scan_railway()
            with self._lock:
                self._railway = result
                self._last_error = ""
        except Exception as exc:  # noqa: BLE001
            log.warning("railway scan failed: %s", exc)
            with self._lock:
                self._last_error = str(exc)
            result = self._railway
        return result

    @staticmethod
    def _scan_railway() -> Dict[str, Any]:
        import asyncio

        from universal_agent.adapters.railway import Railway12306Skill
        from universal_agent.core.contracts import TaskSpec, TaskType
        from universal_agent.coordinator.scanner import RailwayScanCoordinator
        from universal_agent.events import InProcessEventBus
        from universal_agent.registry import MarketplaceManifest, SkillRegistry

        skill = Railway12306Skill()
        health = skill.health_check()
        reg = SkillRegistry()
        reg.register_marketplace(MarketplaceManifest(
            id="railway_12306", domains=["railway"],
            health=health["status"].lower(),
            capabilities={"search": True}, trust={"default_score": 0.85}))
        delivered: list = []

        async def _run() -> Dict[str, Any]:
            coord = RailwayScanCoordinator(
                bus=InProcessEventBus(), registry=reg,
                fetchers={"railway_12306": skill.fetch},
                notifier=delivered.append, top_n=8)
            task = TaskSpec(id="railway-watch-dashboard", type=TaskType.WATCH,
                            domain="railway",
                            search_space={
                                "origin": [RAILWAY_QUERY["from_city"]],
                                "destination": [RAILWAY_QUERY["to_city"]],
                                "departure": {"start": RAILWAY_QUERY["date"]}})
            out = await coord.scan(task)
            return {
                "source_health": health,
                "query": RAILWAY_QUERY,
                "raw_count": len(out.raw_railways),
                "candidate_count": len(out.candidates),
                "ranked": [{
                    "train_no": s["raw"].train_no,
                    "origin": s["raw"].origin_city,
                    "dest": s["raw"].dest_city,
                    "depart": s["raw"].depart_time,
                    "arrive": s["raw"].arrive_time,
                    "seat_class": s["raw"].seat_class,
                    "available": s["raw"].extra.get("available", ""),
                    "score": round(s["score"], 1),
                    "components": {k: round(v, 1) for k, v in s["components"].items()},
                } for s in out.ranked[:12]],
                "opportunity": out.opportunity,
                "notified": out.notified,
                "verification": out.verification,
                "events": out.emitted_events,
            }

        return asyncio.run(_run())


CACHE = ScanCache()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # noqa: ARG002
        pass

    def _json(self, obj: Any, code: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        path = self.path.split("?")[0]
        if path == "/":
            self._serve_html()
        elif path == "/api/health":
            self._json(self._health())
        elif path == "/api/railway":
            self._json(CACHE.railway())
        elif path == "/api/sources":
            self._json(self._sources())
        elif path == "/api/pipeline":
            self._json(PIPELINE)
        else:
            self._json({"error": "not found"}, 404)

    def _serve_html(self) -> None:
        try:
            html = HTML_FILE.read_text("utf-8")
        except FileNotFoundError:
            self._json({"error": "dashboard.html missing"}, 500)
            return
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    @staticmethod
    def _health() -> Dict[str, Any]:
        from universal_agent.service import UniversalAgentService
        svc = UniversalAgentService(Path("/tmp/ua-dashboard-data"))
        try:
            return svc.health()
        finally:
            svc.close()

    @staticmethod
    def _sources() -> Dict[str, Any]:
        statuses: Dict[str, Any] = {}
        # 12306（无 key，实时）
        from universal_agent.adapters.railway import Railway12306Skill
        statuses["railway_12306"] = Railway12306Skill().health_check()
        # 其它源（配置依赖，如实显示）
        import os as _os
        from universal_agent.adapters.kiwi import KiwiTequilaFlightSkill
        statuses["kiwi_tequila"] = KiwiTequilaFlightSkill().health_check()
        statuses["ctrip_http"] = {
            "status": "UNAVAILABLE" if not _os.environ.get("UA_CTRIP_ENDPOINT")
            else "CONFIGURED",
            "reason": "UA_CTRIP_ENDPOINT 未配置" if not _os.environ.get("UA_CTRIP_ENDPOINT")
            else "已配置端点"}
        statuses["booking_http"] = {
            "status": "UNAVAILABLE" if not _os.environ.get("UA_BOOKING_ENDPOINT")
            else "CONFIGURED",
            "reason": "UA_BOOKING_ENDPOINT 未配置" if not _os.environ.get("UA_BOOKING_ENDPOINT")
            else "已配置端点"}
        return {"sources": statuses}


#: SPAC 完整工作循环（看板流转示意）
PIPELINE = {
    "name": "Universal Persistent Watch & Decision",
    "cycle": ["REMEMBER", "WATCH", "SCAN", "NORMALIZE", "VERIFY", "COMPARE",
              "SCORE", "RANK", "DECIDE", "NOTIFY", "PREPARE", "APPROVE",
              "ACT", "VERIFY ACTION", "LEARN", "REMEMBER"],
    "railway": ["SCAN_REQUESTED", "RAW_LISTING_DISCOVERED", "CANDIDATE_CREATED",
                "QUOTE_OBSERVED", "SCORE_UPDATED", "VERIFICATION_COMPLETED",
                "OPPORTUNITY_DETECTED", "NOTIFICATION_REQUESTED",
                "NOTIFICATION_SENT", "SCAN_COMPLETED"],
}


def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Universal Agent 可视化看板")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8632)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    log.info("Dashboard: http://%s:%s", args.host, args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
