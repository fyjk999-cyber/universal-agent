"""Booking HTTP Hotel Skill — Hotel Live Source（FR-082 / CH4-4.4）。

基于通用 HTTP Adapter（FR-060）的 SkillProtocol 实现：
- search()：GET `UA_BOOKING_ENDPOINT`（JSON 契约见下），映射 → RawHotel dict
- fetch()：HotelScan 的 fetcher 契约（返回 List[RawHotel]）
- health_check()：未配置 → UNAVAILABLE（显式）；可达 → HEALTHY
- detail/verify/availability：fail-closed UNVERIFIED/UNKNOWN

JSON 契约（endpoint 返回对象数组，每项）：
  {
    "hotel_id": str, "name": str, "city": "Queenstown", "address": str,
    "check_in": "2026-08-30", "check_out": "2026-09-07",
    "room_name": str, "price_per_night_cny": float, "rating": float, "url": str
  }
缺失关键字段的条目 fail-closed 跳过。
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from ...core.contracts import RawHotel
from ...registry.skills import SkillProtocol
from ..http import HttpAdapter, HttpAdapterError
from ..ctrip.adapter import SkillUnavailable

log = logging.getLogger("ua.adapters.booking")

ENV_ENDPOINT = "UA_BOOKING_ENDPOINT"
ENV_KEY = "UA_BOOKING_KEY"


class BookingHotelSkill(SkillProtocol):
    def __init__(self, http: Optional[HttpAdapter] = None,
                 endpoint: Optional[str] = None,
                 api_key: Optional[str] = None,
                 task_id: str = "booking-http") -> None:
        self.http = http or HttpAdapter()
        self.endpoint = endpoint or os.environ.get(ENV_ENDPOINT) or ""
        self.api_key = api_key or os.environ.get(ENV_KEY) or ""
        self.task_id = task_id
        self.marketplace_id = "booking_http"

    def configured(self) -> bool:
        return bool(self.endpoint)

    # ------------------------------------------------------------------ protocol
    def search(self, query: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not self.configured():
            raise SkillUnavailable(f"{ENV_ENDPOINT} 未配置；Source 显式 UNAVAILABLE")
        params = {k: query.get(k) for k in
                  ("destination", "check_in", "check_out", "nights") if query.get(k)}
        if self.api_key:
            params["key"] = self.api_key
        try:
            payload = self.http.get_json(self.endpoint, params=params)
        except HttpAdapterError as exc:
            raise SkillUnavailable(f"booking_http search failed: {exc}") from exc
        items = payload if isinstance(payload, list) else payload.get("hotels", [])
        return [i for i in items if i.get("hotel_id") and i.get("name")
                and isinstance(i.get("price_per_night_cny"), (int, float))]

    def fetch(self, query) -> List[RawHotel]:
        raw = self.search(query if isinstance(query, dict)
                          else {"destination": query, "check_in": "",
                                "check_out": "", "nights": 0})
        out: List[RawHotel] = []
        for item in raw:
            try:
                out.append(RawHotel(
                    hotel_id=f"{self.marketplace_id}:{item['hotel_id']}",
                    source="booking_http", marketplace_id=self.marketplace_id,
                    task_id=self.task_id, name=item["name"], city=item.get("city", ""),
                    address=item.get("address"), check_in=item.get("check_in", ""),
                    check_out=item.get("check_out", ""), nights=item.get("nights", 0),
                    room_name=item.get("room_name", ""),
                    price_per_night_cny=float(item["price_per_night_cny"]),
                    currency=item.get("currency", "CNY"),
                    rating=float(item.get("rating", 0.0)), url=item.get("url")))
            except Exception as exc:  # noqa: BLE001 — fail-closed
                log.warning("booking_http 跳过坏条目 %s: %s", item.get("hotel_id"), exc)
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


def booking_skill_manifest():
    from universal_agent.core.contracts import SkillManifest
    return SkillManifest(
        skill_id="booking_http.hotel",
        version="0.1.0",
        domains=["hotel"],
        capabilities={"search": True, "detail": False, "availability": False,
                      "price_verify": True, "prepare_order": False,
                      "execute_order": False},
        transport=["http"],
        risk={"execution": "none"},
        description="Booking HTTP JSON 源（FR-060 HTTP Adapter；endpoint 由 UA_BOOKING_ENDPOINT 配置）",
    )


def booking_marketplace_manifest():
    from universal_agent.core.contracts import MarketplaceManifest
    return MarketplaceManifest(
        id="booking_http",
        domains=["hotel"],
        capabilities={"search": True, "price_verify": True},
        trust={"default_score": 0.75},
        health="DEGRADED",
    )
