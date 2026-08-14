"""Tier3 官方源验证骨架（§25 Tier3 / §62）.

设计：对一个候选航班，可选的官方验证源（航司官网 / 官方渠道）。
Phase 4 提供骨架 + 契约 + 健康检查，具体航司适配器按需接入。

合规（§56）：只做公开价格查询页验证；不登录、不购买、不绕过验证码。
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from ...core.contracts import RawListing, VerificationResult
from ...core.verification import FlightVerifier

log = logging.getLogger("ua.adapters.official")


class OfficialSourceRegistry:
    """注册的官方验证源（tier3）。

    每个源实现 `verify(listing) -> VerificationResult`；失败返回 None →
    调用方标记源 DEGRADED（§53）。
    """

    def __init__(self) -> None:
        self._sources: Dict[str, object] = {}
        self._health: Dict[str, str] = {}

    def register(self, source_id: str, verifier: object) -> None:
        self._sources[source_id] = verifier
        self._health[source_id] = "HEALTHY"

    def verify(self, listing: RawListing,
               available: Optional[List[str]] = None) -> Optional[VerificationResult]:
        """依次尝试可用官方源；首个成功即返回。全部失败返回 None。"""
        candidates = available or list(self._sources.keys())
        for sid in candidates:
            if self._health.get(sid) != "HEALTHY":
                continue
            verifier = self._sources.get(sid)
            if verifier is None:
                continue
            try:
                result = verifier.verify(listing)
                if result is not None:
                    return result
            except Exception as exc:  # noqa: BLE001
                log.warning("official source %s failed: %s", sid, exc)
                self._health[sid] = "DEGRADED"
        return None

    def health(self) -> Dict[str, str]:
        return dict(self._health)


class NoOpOfficialVerifier:
    """占位实现：验证结果永远为空（骨架验证用，实际接入在后续 Phase）。

    用途：证明 Tier3 链路（registry → verify → 健康降级）可工作，
    不绑定具体航司。
    """

    def verify(self, listing: RawListing) -> Optional[VerificationResult]:
        return None


class StubOfficialVerifier:
    """测试用假官方源：返回 deterministic 验证结果。"""

    def __init__(self, price: float) -> None:
        self.price = price

    def verify(self, listing: RawListing) -> VerificationResult:
        verifier = FlightVerifier()
        from universal_agent.core.contracts import Money, Quote
        q = Quote(quote_id="official", offer_id=listing.listing_id,
                  price=Money(amount=self.price), method="official_verify",
                  confidence=0.99, source="official-airline")
        return verifier.verify(
            target_key=listing.listing_id, offer_id=listing.listing_id,
            quotes=[q], cross_source_agreement=True, tier="T3")
