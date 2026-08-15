"""12306 Railway Skill — 国内火车真实数据源（FR-110~117 / CH7）。

基于 12306 公开匿名接口（无 key）：
- search()：queryG 余票/时刻 → RawRailway dict（精确车站匹配）
- fetch()：Railway 域 fetcher 契约
- health_check()：车站接口可达 → HEALTHY；否则 UNAVAILABLE

票价 best-effort（leftTicketPrice 被限流时 price 置 None → 归一化 fail-closed）。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ...core.contracts import RawRailway
from ...registry.skills import SkillProtocol
from .client import Railway12306Client, Railway12306Error

log = logging.getLogger("ua.adapters.railway")

SEAT_CLASSES = ["商务座", "一等座", "二等座", "硬卧", "软卧", "硬座", "无座"]


class Railway12306Skill(SkillProtocol):
    def __init__(self, client: Optional[Railway12306Client] = None,
                 task_id: str = "railway-12306",
                 exact_match: bool = True) -> None:
        self.client = client or Railway12306Client()
        self.task_id = task_id
        self.exact_match = exact_match
        self.marketplace_id = "railway_12306"

    # ------------------------------------------------------------------ protocol
    def search(self, query: Dict[str, Any]) -> List[Dict[str, Any]]:
        """查询 → 原始记录 dict 列表（含精确车站过滤）。"""
        try:
            trains = self.client.query_trains(
                query.get("from_city") or query.get("origin", ""),
                query.get("to_city") or query.get("destination", ""),
                query.get("date") or query.get("depart_date", ""),
                exact_match=self.exact_match)
        except Railway12306Error as exc:
            log.warning("railway_12306 search 失败: %s", exc)
            return []
        out: List[Dict[str, Any]] = []
        for t in trains:
            for seat in SEAT_CLASSES:
                avail = t["seats"].get(seat, "")
                if not avail:
                    continue
                out.append({
                    "railway_id": f"{self.marketplace_id}:{t['train_no']}:{seat}",
                    "train_no": t["number"],
                    "origin_city": t["from_city"],
                    "dest_city": t["to_city"],
                    "depart_date": _fmt_date(t["date"]),
                    "depart_time": t["depart"],
                    "arrive_time": t["arrive"],
                    "seat_class": seat,
                    "available": avail,
                })
        return out

    def fetch(self, query) -> List[RawRailway]:
        """Railway 域 fetcher：query = (from_city, to_city, date) 或 dict。"""
        if isinstance(query, tuple) and len(query) == 3:
            q = {"from_city": query[0], "to_city": query[1], "date": query[2]}
        else:
            q = query if isinstance(query, dict) else {}
        items = self.search(q)
        out: List[RawRailway] = []
        for item in items:
            try:
                out.append(RawRailway(
                    railway_id=item["railway_id"], source="railway_12306",
                    marketplace_id=self.marketplace_id, task_id=self.task_id,
                    train_no=item["train_no"],
                    origin_city=item["origin_city"], dest_city=item["dest_city"],
                    depart_date=item["depart_date"], depart_time=item["depart_time"],
                    arrive_time=item["arrive_time"], seat_class=item["seat_class"],
                    price_cny=0.0))  # 票价 best-effort（0.0 → 归一化标 UNKNOWN）
            except Exception as exc:  # noqa: BLE001 — fail-closed
                log.warning("railway_12306 跳过坏记录 %s: %s",
                            item.get("railway_id"), exc)
        return out

    def detail(self, item_key: str) -> Dict[str, Any]:
        return {"status": "UNVERIFIED", "reason": "detail 未接入（fail-closed）"}

    def verify(self, item_key: str) -> Dict[str, Any]:
        return {"status": "UNVERIFIED", "reason": "verify 未接入（fail-closed）"}

    def availability(self, item_key: str) -> Dict[str, Any]:
        return {"status": "UNKNOWN", "reason": "availability 未接入（fail-closed）"}

    def prepare_action(self, item_key: str, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"allowed": False, "reason": "prepare 必须经 ActionGateway/Approval（FR-056）"}

    def health_check(self) -> Dict[str, Any]:
        """FR-055：车站接口可达 → HEALTHY；否则 UNAVAILABLE。"""
        try:
            self.client.stations()
            return {"status": "HEALTHY", "marketplace_id": self.marketplace_id}
        except Railway12306Error as exc:
            return {"status": "UNAVAILABLE", "reason": str(exc)}


def _fmt_date(yyyymmdd: str) -> str:
    if len(yyyymmdd) == 8:
        return f"{yyyymmdd[:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:]}"
    return yyyymmdd


def railway12306_skill_manifest():
    from universal_agent.core.contracts import SkillManifest
    return SkillManifest(
        skill_id="railway_12306",
        version="0.1.0",
        domains=["railway"],
        capabilities={"search": True, "detail": False, "availability": False,
                      "price_verify": False, "prepare_order": False,
                      "execute_order": False},
        transport=["http"],
        risk={"execution": "none"},
        description="12306 公开余票/时刻接口（无 key；精确车站匹配；票价 best-effort）",
    )


def railway12306_marketplace_manifest():
    from universal_agent.core.contracts import MarketplaceManifest
    return MarketplaceManifest(
        id="railway_12306",
        domains=["railway"],
        capabilities={"search": True},
        trust={"default_score": 0.85},
        health="DEGRADED",
    )
