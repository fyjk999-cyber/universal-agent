"""Ctrip Flight Skill — 第二 Flight Live Source（FR-074 / CH4-4.2）。

基于通用 HTTP Adapter（FR-060）的 SkillProtocol 实现：
- search()：GET `UA_CTRIP_ENDPOINT`（JSON 契约见下），映射 → RawListing dict
- fetch()：SearchScan 的 fetcher 契约（FlightQuery → List[RawListing]）
- health_check()：未配置 endpoint → UNAVAILABLE（显式，不静默）；可达 → HEALTHY
- detail/verify/availability：fail-closed UNVERIFIED（合规，不脑补）

JSON 契约（endpoint 返回对象数组，每项）：
  {
    "listing_id": str, "origin": "SHA", "destination": "ZQN",
    "depart_date": "2026-08-30", "return_date": "2026-09-07",
    "price_cny": float, "currency": "CNY",
    "outbound": [{"airline":"CA","flight_no":"451","depart_airport":"SHA",
                  "arrive_airport":"PVG","depart_time":"08:00","arrive_time":"09:10"}],
    "inbound": [...同构...],
    "stops": int, "duration_min": int, "url": str
  }
缺失关键字段的条目按 fail-closed 跳过（不伪造）。
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ...core.contracts import RawLeg, RawListing, RawSegment
from ...coordinator.query_planner import FlightQuery
from ...registry.skills import SkillProtocol
from ..http import HttpAdapter, HttpAdapterError

log = logging.getLogger("ua.adapters.ctrip")

ENV_ENDPOINT = "UA_CTRIP_ENDPOINT"
ENV_KEY = "UA_CTRIP_KEY"


class SkillUnavailable(RuntimeError):
    """Source 未配置或不可达（调用方应标 DEGRADED/UNAVAILABLE，不中断整体）。"""


class CtripFlightSkill(SkillProtocol):
    def __init__(self, http: Optional[HttpAdapter] = None,
                 endpoint: Optional[str] = None,
                 api_key: Optional[str] = None,
                 task_id: str = "ctrip-http") -> None:
        self.http = http or HttpAdapter()
        self.endpoint = endpoint or os.environ.get(ENV_ENDPOINT) or ""
        self.api_key = api_key or os.environ.get(ENV_KEY) or ""
        self.task_id = task_id
        self.marketplace_id = "ctrip_http"

    # ------------------------------------------------------------------ config
    def configured(self) -> bool:
        return bool(self.endpoint)

    # ------------------------------------------------------------------ protocol
    def search(self, query: Dict[str, Any]) -> List[Dict[str, Any]]:
        """SkillProtocol.search：查询 → RawListing dict 列表（fail-closed）。"""
        if not self.configured():
            raise SkillUnavailable(f"{ENV_ENDPOINT} 未配置；Source 显式 UNAVAILABLE")
        params = {"origin": query.get("origin"), "destination": query.get("destination"),
                  "depart": query.get("depart_date"), "return": query.get("return_date"),
                  "nights": query.get("nights")}
        if self.api_key:
            params["key"] = self.api_key
        try:
            payload = self.http.get_json(self.endpoint, params=params)
        except HttpAdapterError as exc:
            raise SkillUnavailable(f"ctrip_http search failed: {exc}") from exc
        items = payload if isinstance(payload, list) else payload.get("listings", [])
        return [i for i in items if self._valid(i)]

    def fetch(self, query: FlightQuery) -> List[RawListing]:
        """SearchScan fetcher 契约（同步；scanner 经 to_thread 调用）。"""
        raw_dicts = self.search({
            "origin": query.origin, "destination": query.destination,
            "depart_date": query.depart_date, "return_date": query.return_date,
            "nights": query.nights})
        return [self._to_raw(item, query) for item in raw_dicts]

    def detail(self, item_key: str) -> Dict[str, Any]:
        return {"status": "UNVERIFIED", "reason": "detail 未接入（fail-closed）"}

    def verify(self, item_key: str) -> Dict[str, Any]:
        return {"status": "UNVERIFIED", "reason": "verify 未接入（fail-closed）"}

    def availability(self, item_key: str) -> Dict[str, Any]:
        return {"status": "UNKNOWN", "reason": "availability 未接入（fail-closed）"}

    def prepare_action(self, item_key: str, params: Dict[str, Any]) -> Dict[str, Any]:
        # FR-056：Skill 不得执行；L2+ 必须走 ActionGateway + Approval
        return {"allowed": False, "reason": "prepare 必须经 ActionGateway/Approval（FR-056）"}

    def health_check(self) -> Dict[str, Any]:
        """FR-055：HEALTHY / UNAVAILABLE / AUTH_REQUIRED（显式状态）。"""
        if not self.configured():
            return {"status": "UNAVAILABLE",
                    "reason": f"{ENV_ENDPOINT} 未配置（显式，非静默降级）"}
        try:
            ok = self.http.is_available(self.endpoint)
        except HttpAdapterError:
            ok = False
        if not ok:
            return {"status": "UNAVAILABLE", "reason": f"endpoint 不可达: {self.endpoint}"}
        if self.api_key == "":
            return {"status": "AUTH_REQUIRED",
                    "reason": f"{ENV_KEY} 未配置；匿名访问可能受限"}
        return {"status": "HEALTHY", "marketplace_id": self.marketplace_id}

    # ------------------------------------------------------------------ mapping
    def _valid(self, item: Dict[str, Any]) -> bool:
        """fail-closed：关键字段缺失的条目跳过，不伪造。"""
        return bool(item.get("listing_id") and item.get("origin")
                    and item.get("destination") and item.get("price_cny")
                    and isinstance(item.get("price_cny"), (int, float))
                    and item.get("depart_date") and item.get("return_date")
                    and item.get("outbound") and item.get("inbound"))

    def _to_raw(self, item: Dict[str, Any], query: FlightQuery) -> RawListing:
        try:
            def _leg(segs: List[Dict[str, Any]], fallback_date: str) -> RawLeg:
                return RawLeg(segments=[RawSegment(
                    airline=s.get("airline", "?"), flight_no=s.get("flight_no", "?"),
                    dep_airport=s.get("depart_airport", s.get("dep_airport", "?")),
                    arr_airport=s.get("arrive_airport", s.get("arr_airport", "?")),
                    dep_time=s.get("depart_time", s.get("dep_time", "00:00")),
                    arr_time=s.get("arrive_time", s.get("arr_time", "00:00")),
                    dep_date=s.get("dep_date", fallback_date),
                    arr_date=s.get("arr_date", fallback_date),
                    duration_min=int(s.get("duration_min", 0)),
                    cabin=s.get("cabin", "economy")) for s in segs],
                    total_min=int(item.get("duration_min", 0)),
                    stops=int(item.get("stops", -1)))
            return RawListing(
                listing_id=f"{self.marketplace_id}:{item['listing_id']}",
                source="ctrip_http", marketplace_id=self.marketplace_id,
                task_id=self.task_id,
                origin_airport=item["origin"], dest_airport=item["destination"],
                depart_date=item["depart_date"], return_date=item["return_date"],
                nights=query.nights,
                price_cny=float(item["price_cny"]),
                currency=item.get("currency", "CNY"),
                outbound=_leg(item["outbound"], query.depart_date),
                inbound=_leg(item["inbound"], query.return_date),
                url=item.get("url"),
                extra={"stops": item.get("stops", -1),
                       "duration_min": item.get("duration_min", 0)})
        except Exception as exc:  # noqa: BLE001 — fail-closed：坏条目跳过
            log.warning("ctrip_http 跳过坏条目 %s: %s", item.get("listing_id"), exc)
            raise ValueError(f"bad ctrip_http listing: {exc}") from exc


def ctrip_skill_manifest():
    """Skill 能力声明（search 真实；detail/verify/availability fail-closed）。"""
    from universal_agent.core.contracts import SkillManifest
    return SkillManifest(
        skill_id="ctrip_http.flight",
        version="0.1.0",
        domains=["flight"],
        capabilities={"search": True, "detail": False, "availability": False,
                      "price_verify": True, "prepare_order": False,
                      "execute_order": False},
        transport=["http"],
        risk={"execution": "none"},
        description="Ctrip HTTP JSON 源（FR-060 HTTP Adapter；endpoint 由 UA_CTRIP_ENDPOINT 配置）",
    )


def ctrip_marketplace_manifest():
    """Source 注册信息（health 初始 DEGRADED：未验证真实端点前不冒充 HEALTHY）。"""
    from universal_agent.core.contracts import MarketplaceManifest
    return MarketplaceManifest(
        id="ctrip_http",
        domains=["flight"],
        capabilities={"search": True, "price_verify": True},
        trust={"default_score": 0.75},
        health="DEGRADED",
    )
