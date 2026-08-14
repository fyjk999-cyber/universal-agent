"""Hotel domain knowledge (RULE 3).

Hotel Entity Resolution key (§21):
    name | geo(lat,lng) | brand | address
Two sources seeing the same real hotel must produce the same key.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ...core.contracts import RawHotel


def entity_key(raw: "RawHotel") -> str:
    """Deterministic hotel entity key: name + geo + brand."""
    parts = [raw.name.strip().lower()]
    if raw.lat and raw.lng:
        parts.append(f"{raw.lat:.3f}|{raw.lng:.3f}")
    if raw.brand:
        parts.append(raw.brand.lower())
    if raw.address:
        parts.append(raw.address.strip().lower())
    return "|".join(parts)


@dataclass(frozen=True)
class HotelNorm:
    """Room normalization (§63): normalize room name/grade to a standard."""
    room_grade: str = "standard"  # standard | superior | deluxe | suite
    bed_type: str = "unknown"     # king | twin | double | unknown
    board: str = "none"           # none | breakfast | half | full


def normalize_room(room_name: str) -> HotelNorm:
    """Normalize free-text room names to (grade, bed, board).

    纯规则（RULE 7），用于跨平台比较同一房型。
    """
    name = (room_name or "").lower()
    if any(k in name for k in ("suite", "套房")):
        grade = "suite"
    elif any(k in name for k in ("deluxe", "豪华", "尊贵")):
        grade = "deluxe"
    elif any(k in name for k in ("superior", "高级", "精选")):
        grade = "superior"
    else:
        grade = "standard"

    if any(k in name for k in ("king", "大床")):
        bed = "king"
    elif any(k in name for k in ("twin", "双床")):
        bed = "twin"
    elif any(k in name for k in ("double", "双人")):
        bed = "double"
    else:
        bed = "unknown"

    if any(k in name for k in ("all inclusive", "全包", "三餐")):
        board = "full"
    elif any(k in name for k in ("half board", "半餐", "早晚餐")):
        board = "half"
    elif any(k in name for k in ("breakfast", "含早", "早餐")):
        board = "breakfast"
    else:
        board = "none"

    return HotelNorm(room_grade=grade, bed_type=bed, board=board)


def score_room(grade: str) -> int:
    """Room grade → quality rank for scoring (higher better)."""
    return {"standard": 1, "superior": 2, "deluxe": 3, "suite": 4}.get(grade, 1)
