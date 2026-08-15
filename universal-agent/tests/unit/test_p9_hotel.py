"""P9 — Hotel Live：breakfast/cancellation/tax/occupancy 归一化。

验收：
1. normalize_policy：从房型文本/extra 解析 breakfast/cancellation/tax/occupancy
2. 未知 → UNKNOWN（fail-closed，不猜 "included"/"refundable"）
3. RawHotel → normalized terms 进入 Candidate/Offer
4. 跨平台房型比较可用（同一房型不同源 → 同一 norm）
"""
from __future__ import annotations

from pathlib import Path

import pytest

from universal_agent.core.contracts import RawHotel
from universal_agent.domains.hotel import normalize_hotel
from universal_agent.domains.hotel.knowledge import normalize_room, normalize_policy


def _hotel(**kw) -> RawHotel:
    base = dict(
        hotel_id="h1", source="ctrip", marketplace_id="ctrip", task_id="t1",
        name="Grand Hotel", city="ZQN", room_name="Deluxe King with Breakfast",
        price_per_night_cny=1500.0, check_in="2026-08-30", check_out="2026-09-06",
        nights=7,
    )
    base.update(kw)
    return RawHotel(**base)


def test_room_norm_breakfast() -> None:
    norm = normalize_room("Deluxe King with Breakfast")
    assert norm.board == "breakfast"
    assert norm.bed_type == "king"
    assert norm.room_grade == "deluxe"


def test_room_norm_unknown_bed_is_unknown() -> None:
    """未知床型 → unknown（不猜）。"""
    norm = normalize_room("Standard Room")
    assert norm.bed_type == "unknown"


def test_normalize_policy_from_extra() -> None:
    """从 extra 解析早餐/取消/税/入住政策。"""
    raw = _hotel(extra={
        "breakfast": "included", "cancellation": "free_before_24h",
        "tax": 0.15, "occupancy": {"max_guests": 2},
    })
    pol = normalize_policy(raw)
    assert pol.breakfast == "included"
    assert pol.cancellation == "free_before_24h"
    assert pol.tax == 0.15
    assert pol.occupancy_max == 2


def test_normalize_policy_unknown_is_unknown() -> None:
    """未知政策 → UNKNOWN（fail-closed）。"""
    raw = _hotel(room_name="Standard Room", extra={})
    pol = normalize_policy(raw)
    assert pol.breakfast == "UNKNOWN"
    assert pol.cancellation == "UNKNOWN"
    assert pol.occupancy_max is None


def test_normalize_policy_parses_free_text() -> None:
    """从房型文本解析政策关键词。"""
    raw = _hotel(room_name="King Room - Free Cancellation", extra={})
    pol = normalize_policy(raw)
    assert pol.cancellation == "free"


def test_hotel_normalize_embeds_policy_terms() -> None:
    """政策进入 Candidate/Offer terms。"""
    raw = _hotel(extra={"breakfast": "included", "cancellation": "free",
                        "tax": 0.15})
    cand, offer, quote, _ = normalize_hotel(raw, "t1")
    terms = offer.terms
    assert terms.get("breakfast") == "included"
    assert terms.get("cancellation") == "free"
    assert terms.get("tax") == 0.15
