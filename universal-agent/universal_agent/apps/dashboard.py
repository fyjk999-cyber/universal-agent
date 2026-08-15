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
DEFAULT_QUERY = {"from": "上海", "to": "杭州东", "date": "2026-08-20"}


class ScanCache:
    """带 TTL 的扫描结果缓存（后台线程刷新，锁保护；按查询参数分桶）。"""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._railway: Dict[str, Any] = {}
        self._railway_at: float = 0.0
        self._last_error: str = ""

    def railway(self, query: Dict[str, str] | None = None,
                force: bool = False) -> Dict[str, Any]:
        q = {k: (query or {}).get(k) or v for k, v in DEFAULT_QUERY.items()}
        now = time.time()
        with self._lock:
            fresh = (self._railway.get("query") == q
                     and (now - self._railway_at) <= CACHE_TTL)
            if fresh and not force:
                return self._railway
            self._railway_at = now
        try:
            result = self._scan_railway(q)
            self._record_history(result)
            with self._lock:
                self._railway = result
                self._last_error = ""
        except Exception as exc:  # noqa: BLE001
            log.warning("railway scan failed: %s", exc)
            with self._lock:
                self._last_error = str(exc)
            result = self._railway
        return result

    # ------------------------------------------------------------------ history
    def _record_history(self, result: Dict[str, Any]) -> None:
        """每次扫描写入余票/得分历史（SQLite，看板趋势曲线）。"""
        from datetime import datetime, timezone
        from universal_agent.persistence import Database

        ranked = result.get("ranked") or []
        if not ranked:
            return
        db = Database(self.data_dir / "universal_agent.db")
        try:
            now = datetime.now(timezone.utc).isoformat()
            q = result.get("query", {})
            route = f"{q.get('from','')}->{q.get('to','')}"
            for r in ranked[:10]:
                db.execute(
                    "INSERT INTO railway_history "
                    "(route, query_date, train_no, seat_class, available, score, created_at) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (route, q.get("date", ""), r.get("train_no", ""),
                     r.get("seat_class", ""), str(r.get("available", "")),
                     float(r.get("score", 0.0)), now))
        finally:
            db.close()

    def history(self, query: Dict[str, str] | None = None,
                limit: int = 60) -> Dict[str, Any]:
        """余票/得分时间序列（看板曲线）。"""
        from universal_agent.persistence import Database

        q = query or {}
        db = Database(self.data_dir / "universal_agent.db")
        try:
            route = f"{q.get('from','')}->{q.get('to','')}"
            sql = ("SELECT train_no, seat_class, available, score, created_at "
                   "FROM railway_history WHERE route=? AND query_date=? "
                   "ORDER BY id DESC LIMIT ?")
            rows = db.query_all(sql, (route, q.get("date", ""), int(limit)))
        finally:
            db.close()
        rows.reverse()  # 时间正序
        return {"history": [
            {"train_no": r["train_no"], "seat_class": r["seat_class"],
             "available": r["available"], "score": r["score"],
             "created_at": r["created_at"]} for r in rows]}

    @staticmethod
    def _scan_railway(q: Dict[str, str]) -> Dict[str, Any]:
        import asyncio
        import time as _t

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
                                "origin": [q["from"]],
                                "destination": [q["to"]],
                                "departure": {"start": q["date"]}})
            out = await coord.scan(task)
            ranked = []
            # 实时票价（best-effort：官方票价端点匿名受限；成功才显示，否则 fail-closed）
            for idx, s in enumerate(out.ranked[:12]):
                raw = s["raw"]
                price = None
                if idx < 3:  # 只对 Top3 尝试票价（限流友好）
                    tn_id = raw.extra.get("train_no_id", "")
                    if tn_id:
                        try:
                            price = skill.client.query_price(
                                tn_id, skill.client.code(raw.origin_city),
                                skill.client.code(raw.dest_city), raw.depart_date)
                        except Exception:  # noqa: BLE001
                            price = None
                    _t.sleep(1.2)
                ranked.append({
                    "train_no": raw.train_no,
                    "origin": raw.origin_city,
                    "dest": raw.dest_city,
                    "depart": raw.depart_time,
                    "arrive": raw.arrive_time,
                    "seat_class": raw.seat_class,
                    "available": raw.extra.get("available", ""),
                    "available_label": raw.extra.get("available_label", ""),
                    "price": price,
                    "score": round(s["score"], 1),
                    "components": {k: round(v, 1) for k, v in s["components"].items()},
                })
            return {
                "source_health": health,
                "query": q,
                "raw_count": len(out.raw_railways),
                "candidate_count": len(out.candidates),
                "ranked": ranked,
                "opportunity": out.opportunity,
                "notified": out.notified,
                "verification": out.verification,
                "events": out.emitted_events,
            }

        return asyncio.run(_run())


CACHE = ScanCache(Path("/tmp/ua-dashboard-data"))


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
        from urllib.parse import parse_qs, urlparse
        parsed = urlparse(self.path)
        path = parsed.path

        def _fix(v: str) -> str:
            # 容忍未 percent-encode 的原始 UTF-8（curl 测试）；浏览器编码值原样返回
            try:
                return v.encode("latin-1").decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                return v

        params = {k: _fix(v[0]) for k, v in parse_qs(parsed.query).items()}
        if path == "/":
            self._serve_html()
        elif path == "/api/health":
            self._json(self._health())
        elif path == "/api/railway":
            self._json(CACHE.railway(params, force=params.pop("refresh", False)))
        elif path == "/api/railway/history":
            self._json(CACHE.history(params))
        elif path == "/api/sources":
            self._json(self._sources())
        elif path == "/api/pipeline":
            self._json(PIPELINE)
        elif path == "/api/stations":
            self._json(self._stations())
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
    def _stations() -> Dict[str, Any]:
        """常用车站（看板切换地址用；完整 3384 站可后续搜索）。"""
        return {"stations": ["上海", "上海虹桥", "杭州", "杭州东", "杭州西",
                             "南京", "南京南", "苏州", "北京", "北京南",
                             "广州", "广州南", "深圳", "深圳北", "成都东",
                             "重庆北", "武汉", "西安北", "天津", "厦门北"]}

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
