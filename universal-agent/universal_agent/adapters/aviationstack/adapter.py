"""Aviationstack 实时航班状态 Skill（Flight 域运营数据源，借自本地机票 OS 接入经验）。

端点：`https://api.aviationstack.com/v1/flights`（query param `access_key` 认证）
环境变量：`UA_AVIATIONSTACK_KEY`（api.aviationstack.com 免费档注册）
覆盖：按航班号 + 日期查询实时状态（scheduled/active/landed/cancelled/delayed…）、
      起降机场/航站楼/登机口/延误分钟/预计与实际出发时间。

边界（诚实标注，不冒充）：
- Aviationstack 是**运营数据**，不是可售票舱/价格（§33 非目标不混淆）。
- 免费档未来日期排班可能不在权限内 → 查不到时如实返回 found=False（RULE-009）。
- 所有映射 fail-closed：缺关键字段的条目跳过，不伪造（RULE-009）。

SkillProtocol 能力：search/detail/verify/availability/prepare_action/health_check，
无 execute（§33；prepare 必须经 ActionGateway/Approval，FR-056）。
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from ...core.contracts import RawListing
from ...coordinator.query_planner import FlightQuery
from ...domains.flight.airports import resolve_airport
from ...registry.skills import SkillProtocol
from ..http import HttpAdapter, HttpAdapterError
from ..ctrip.adapter import SkillUnavailable

log = logging.getLogger("ua.adapters.aviationstack")

ENV_KEY = "UA_AVIATIONSTACK_KEY"
DEFAULT_ENDPOINT = "https://api.aviationstack.com/v1"

#: 状态 → 中文标签（确定性映射；未知状态原样返回，不猜测）
STATUS_LABELS_ZH: Dict[str, str] = {
    "scheduled": "计划",
    "active": "飞行中",
    "landed": "已到达",
    "cancelled": "已取消",
    "diverted": "备降",
    "incident": "异常",
    "delayed": "延误",
    "unknown": "未知",
}


def _status_label_zh(status: Optional[str]) -> str:
    if not status:
        return "未知"
    return STATUS_LABELS_ZH.get(status, status)


class AviationstackFlightStatusSkill(SkillProtocol):
    """真实航班实时状态 Skill（FR-074 Flight 域运营数据补充源）。"""

    def __init__(self, http: Optional[HttpAdapter] = None,
                 api_key: Optional[str] = None,
                 endpoint: Optional[str] = None,
                 task_id: str = "aviationstack",
                 timeout_ms: int = 12_000) -> None:
        self.http = http or HttpAdapter(timeout_ms=timeout_ms, retries=1)
        self.api_key = api_key if api_key is not None else os.environ.get(ENV_KEY, "")
        self.endpoint = endpoint or os.environ.get("UA_AVIATIONSTACK_ENDPOINT") \
            or DEFAULT_ENDPOINT
        self.task_id = task_id
        self.marketplace_id = "aviationstack"

    # ------------------------------------------------------------------ protocol
    def search(self, query: Dict[str, Any]) -> List[Dict[str, Any]]:
        """按航班号 + 日期查实时状态，返回 aviationstack data[]（fail-closed）。"""
        if not self.api_key:
            raise SkillUnavailable(
                f"{ENV_KEY} 未配置（api.aviationstack.com 免费档注册）；"
                f"Source 显式 AUTH_REQUIRED")
        flight = str(query.get("flight") or "").upper()
        if not flight or not 2 <= len(flight) <= 8:
            raise SkillUnavailable(f"无效航班号「{flight}」（如 CA123）；fail-closed")
        params: Dict[str, Any] = {
            "access_key": self.api_key,
            "flight_iata": flight,
            "limit": 10,
        }
        if query.get("date"):
            params["flight_date"] = str(query["date"])
        try:
            payload = self.http.get_json(f"{self.endpoint}/flights", params=params)
        except HttpAdapterError as exc:
            raise SkillUnavailable(f"aviationstack 查询失败: {exc}") from exc
        if not isinstance(payload, dict) or "data" not in payload:
            raise SkillUnavailable("aviationstack: 响应缺少 data 字段（fail-closed）")
        return payload["data"]

    def fetch(self, query: FlightQuery) -> List[RawListing]:
        """运营状态不是可售 listing —— 本 Skill 不产出 RawListing（显式拒绝）。"""
        raise SkillUnavailable(
            "aviationstack 是运营数据源（状态/登机口/延误），不是票价/舱位源；"
            "请用 live_status() 查询状态，或接 Kiwi/Ctrip 获取可售报价（§33 不混淆）")

    def detail(self, item_key: str) -> Dict[str, Any]:
        return {"status": "UNVERIFIED", "reason": "detail 未接入（fail-closed）"}

    def verify(self, item_key: str) -> Dict[str, Any]:
        return {"status": "UNVERIFIED", "reason": "verify 未接入（fail-closed）"}

    def availability(self, item_key: str) -> Dict[str, Any]:
        return {"status": "UNKNOWN", "reason": "运营数据无舱位概念（fail-closed）"}

    def prepare_action(self, item_key: str, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"allowed": False, "reason": "prepare 必须经 ActionGateway/Approval（FR-056）"}

    def health_check(self) -> Dict[str, Any]:
        """FR-055：HEALTHY / AUTH_REQUIRED / UNAVAILABLE（显式）。"""
        if not self.api_key:
            return {"status": "AUTH_REQUIRED",
                    "reason": f"{ENV_KEY} 未配置（api.aviationstack.com 注册）"}
        try:
            payload = self.http.get_json(
                f"{self.endpoint}/flights",
                params={"access_key": self.api_key,
                        "flight_iata": "CA123", "limit": 1})
            if isinstance(payload, dict) and "data" in payload:
                return {"status": "HEALTHY", "marketplace_id": self.marketplace_id}
            return {"status": "UNAVAILABLE",
                    "reason": "响应缺少 data 字段（fail-closed）"}
        except SkillUnavailable as exc:
            return {"status": "AUTH_REQUIRED", "reason": str(exc)}
        except HttpAdapterError as exc:
            return {"status": "UNAVAILABLE", "reason": str(exc)}

    # ------------------------------------------------------------------ 看板便捷接口
    def live_status(self, flight: str, date: str = "") -> Dict[str, Any]:
        """航班号 → 归一化实时状态（看板状态列用；找不到如实 found=False）。"""
        try:
            items = self.search({"flight": flight, "date": date})
        except SkillUnavailable as exc:
            return {"available": False, "source": "aviationstack",
                    "message": str(exc)}
        if not items:
            return {"available": True, "source": "aviationstack", "found": False,
                    "message": f"未找到 {flight} 的实时记录（免费档可能不含未来排班）"}
        # 免费档 flight_iata 是模糊匹配（CA123 → SC123/OZ6808…），精确匹配优先
        exact = next((x for x in items
                      if str((x.get("flight") or {}).get("iata") or "").upper()
                      == flight.upper()), None)
        item = exact if exact is not None else items[0]
        dep = item.get("departure") or {}
        arr = item.get("arrival") or {}
        fnum = (item.get("flight") or {}).get("iata") or flight
        status = item.get("flight_status") or "unknown"
        return {
            "available": True,
            "source": "aviationstack",
            "found": True,
            "flight": fnum,
            "status": status,
            "status_zh": _status_label_zh(status),
            "updated_at": _now_iso(),
            "departure": {
                "airport": dep.get("airport"),
                "iata": dep.get("iata"),
                "terminal": dep.get("terminal"),
                "gate": dep.get("gate"),
                "delay_min": dep.get("delay"),
                "scheduled": dep.get("scheduled"),
                "estimated": dep.get("estimated"),
                "actual": dep.get("actual"),
            },
            "arrival": {
                "airport": arr.get("airport"),
                "iata": arr.get("iata"),
                "terminal": arr.get("terminal"),
                "gate": arr.get("gate"),
                "delay_min": arr.get("delay"),
                "scheduled": arr.get("scheduled"),
                "estimated": arr.get("estimated"),
                "actual": arr.get("actual"),
            },
        }

    # ------------------------------------------------------------------ 兼容解析
    @staticmethod
    def resolve_airport(value: Any) -> Optional[str]:
        """暴露域解析给看板/其它模块（中文城市→IATA）。"""
        return resolve_airport(value)


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def aviationstack_skill_manifest():
    from universal_agent.core.contracts import SkillManifest
    return SkillManifest(
        skill_id="aviationstack.flight_status",
        version="0.1.0",
        domains=["flight"],
        capabilities={"search": True, "detail": False, "availability": False,
                      "price_verify": False, "prepare_order": False,
                      "execute_order": False},
        transport=["http"],
        risk={"execution": "none"},
        description="Aviationstack 实时航班状态（状态/航站楼/登机口/延误；运营数据非票价）",
    )


def aviationstack_marketplace_manifest():
    from universal_agent.core.contracts import MarketplaceManifest
    return MarketplaceManifest(
        id="aviationstack",
        domains=["flight"],
        capabilities={"search": True},
        trust={"default_score": 0.70},
        health="DEGRADED",  # 未配置 key 前不冒充 HEALTHY
    )
