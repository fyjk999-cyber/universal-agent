"""Kiwi Tequila Flight Skill — 真实 Flight 价格 API（FR-074 第二 Live 源）。

Tequila API（Kiwi.com）：
- 端点：`https://tequila-api.kiwi.com/v2`（默认），可用 `UA_KIWI_ENDPOINT` 覆盖
- 认证：`apikey` header（`UA_KIWI_KEY`；partners.kiwi.com 注册，免费档见 README）
- 覆盖：全球航线（含 SHA/PVG/HGH → ZQN Queenstown），真实实时价格
- 合规：公开搜索端点 + apikey；不做登录态/绕过风控（SPAC §33）

响应映射（fail-closed）：
  data[]: { id, flyFrom, flyTo, cityFrom, cityTo, price, deep_link,
            route[]: { flyFrom, flyTo, cityFrom, cityTo, airline, flight_no,
                       departure{utc}, arrival{utc}, return: 0|1 } }
→ RawListing（outbound = route 中 return=0 的航段；inbound = return=1 的航段）
缺失关键字段的条目跳过，不伪造（RULE-009）。
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from ...core.contracts import RawLeg, RawListing, RawSegment
from ...coordinator.query_planner import FlightQuery
from ...registry.skills import SkillProtocol
from ..http import HttpAdapter, HttpAdapterError
from ..ctrip.adapter import SkillUnavailable

log = logging.getLogger("ua.adapters.kiwi")

ENV_KEY = "UA_KIWI_KEY"
ENV_ENDPOINT = "UA_KIWI_ENDPOINT"
DEFAULT_ENDPOINT = "https://tequila-api.kiwi.com/v2"


class KiwiTequilaFlightSkill(SkillProtocol):
    def __init__(self, http: Optional[HttpAdapter] = None,
                 api_key: Optional[str] = None,
                 endpoint: Optional[str] = None,
                 task_id: str = "kiwi-tequila",
                 currency: str = "CNY") -> None:
        self.http = http or HttpAdapter()
        self.api_key = api_key if api_key is not None else os.environ.get(ENV_KEY, "")
        self.endpoint = (endpoint or os.environ.get(ENV_ENDPOINT) or DEFAULT_ENDPOINT)
        self.task_id = task_id
        self.currency = currency
        self.marketplace_id = "kiwi_tequila"

    # ------------------------------------------------------------------ protocol
    def search(self, query: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not self.api_key:
            raise SkillUnavailable(
                f"{ENV_KEY} 未配置（partners.kiwi.com 注册免费 key）；Source 显式 AUTH_REQUIRED")
        params = {
            "fly_from": query.get("origin"), "fly_to": query.get("destination"),
            "date_from": _tequila_date(query.get("depart_date")),
            "date_to": _tequila_date(query.get("depart_date")),
            "return_from": _tequila_date(query.get("return_date")),
            "return_to": _tequila_date(query.get("return_date")),
            "curr": query.get("currency", self.currency),
            "max_stopovers": 4, "limit": 10,
        }
        try:
            payload = self.http.get_json(
                f"{self.endpoint}/search", params={k: v for k, v in params.items() if v},
                headers={"apikey": self.api_key})
        except HttpAdapterError as exc:
            raise SkillUnavailable(f"kiwi search failed: {exc}") from exc
        if not isinstance(payload, dict) or "data" not in payload:
            raise SkillUnavailable("kiwi search: 响应缺少 data 字段（fail-closed）")
        return payload["data"]

    def fetch(self, query: FlightQuery) -> List[RawListing]:
        items = self.search({
            "origin": query.origin, "destination": query.destination,
            "depart_date": query.depart_date, "return_date": query.return_date,
            "nights": query.nights, "currency": self.currency})
        out: List[RawListing] = []
        for item in items:
            try:
                raw = self._to_raw(item, query)
                if raw is not None:
                    out.append(raw)
            except Exception as exc:  # noqa: BLE001 — fail-closed：坏条目跳过
                log.warning("kiwi 跳过坏条目 %s: %s", item.get("id"), exc)
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
        """FR-055：HEALTHY / AUTH_REQUIRED / UNAVAILABLE（显式）。"""
        if not self.api_key:
            return {"status": "AUTH_REQUIRED",
                    "reason": f"{ENV_KEY} 未配置（partners.kiwi.com 注册）"}
        try:
            # 轻量探测：search 端点（限 1 条）作为可达性 + 认证验证
            self.http.get_json(
                f"{self.endpoint}/search",
                params={"fly_from": "SHA", "fly_to": "ZQN",
                        "date_from": "30/08/2026", "date_to": "03/09/2026",
                        "limit": 1, "curr": self.currency},
                headers={"apikey": self.api_key})
            return {"status": "HEALTHY", "marketplace_id": self.marketplace_id}
        except SkillUnavailable as exc:
            return {"status": "AUTH_REQUIRED", "reason": str(exc)}
        except HttpAdapterError as exc:
            return {"status": "UNAVAILABLE", "reason": str(exc)}

    # ------------------------------------------------------------------ mapping
    def _to_raw(self, item: Dict[str, Any], query: FlightQuery) -> Optional[RawListing]:
        price = item.get("price")
        if not isinstance(price, (int, float)):
            return None
        routes = item.get("route") or []
        outbound = [r for r in routes if not r.get("return")]
        inbound = [r for r in routes if r.get("return")]
        if not outbound:
            return None
        depart = _leg_date(outbound[0].get("departure"))
        ret = _leg_date(inbound[0].get("arrival")) if inbound else None
        if not depart:
            return None
        return RawListing(
            listing_id=f"kiwi:{item.get('id', hash(str(item)) & 0xffff)}",
            source="kiwi_tequila", marketplace_id=self.marketplace_id,
            task_id=self.task_id,
            origin_airport=outbound[0].get("flyFrom", query.origin),
            dest_airport=outbound[-1].get("flyTo", query.destination),
            depart_date=depart, return_date=ret or query.return_date,
            nights=query.nights,
            price_cny=float(price), currency=self.currency,
            outbound=RawLeg(segments=[_segment(r, depart) for r in outbound],
                            stops=max(0, len(outbound) - 1)),
            inbound=RawLeg(segments=[_segment(r, ret or query.return_date)
                                     for r in inbound],
                           stops=max(0, len(inbound) - 1)) if inbound else RawLeg(),
            url=item.get("deep_link"),
            extra={"kiwi_search_id": item.get("id")})


def _tequila_date(iso: str) -> str:
    """YYYY-MM-DD → DD/MM/YYYY（Tequila 日期格式）。"""
    if not iso:
        return ""
    try:
        y, m, d = iso.split("-")
        return f"{d}/{m}/{y}"
    except ValueError:
        return iso


def _leg_date(departure: Any) -> str:
    """Tequila departure{utc} → YYYY-MM-DD（本地容错）。"""
    if isinstance(departure, dict):
        utc = departure.get("utc") or departure.get("local") or ""
        return utc[:10]
    if isinstance(departure, str):
        return departure[:10]
    return ""


def _segment(route: Dict[str, Any], date: str) -> RawSegment:
    return RawSegment(
        airline=route.get("airline") or "?", flight_no=str(route.get("flight_no") or "?"),
        dep_airport=route.get("flyFrom") or "?", arr_airport=route.get("flyTo") or "?",
        dep_time=(route.get("departure") or {}).get("utc", "00:00")[11:16]
        if isinstance(route.get("departure"), dict) else "00:00",
        arr_time=(route.get("arrival") or {}).get("utc", "00:00")[11:16]
        if isinstance(route.get("arrival"), dict) else "00:00",
        dep_date=date, arr_date=date, duration_min=0)


def kiwi_skill_manifest():
    from universal_agent.core.contracts import SkillManifest
    return SkillManifest(
        skill_id="kiwi_tequila.flight",
        version="0.1.0",
        domains=["flight"],
        capabilities={"search": True, "detail": False, "availability": False,
                      "price_verify": True, "prepare_order": False,
                      "execute_order": False},
        transport=["http"],
        risk={"execution": "none"},
        description="Kiwi Tequila 真实航班价格 API（apikey 认证；全球航线含 ZQN）",
    )


def kiwi_marketplace_manifest():
    from universal_agent.core.contracts import MarketplaceManifest
    return MarketplaceManifest(
        id="kiwi_tequila",
        domains=["flight"],
        capabilities={"search": True, "price_verify": True},
        trust={"default_score": 0.82},
        health="DEGRADED",  # 未配置 key 前不冒充 HEALTHY
    )
