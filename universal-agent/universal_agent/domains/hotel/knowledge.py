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


@dataclass(frozen=True)
class HotelPolicy:
    """P9: 政策归一化（早餐/取消/税/入住人数）。未知 → UNKNOWN（fail-closed）。"""
    breakfast: str = "UNKNOWN"       # included | not_included | UNKNOWN
    cancellation: str = "UNKNOWN"    # free | non_refundable | free_before_Nh | UNKNOWN
    tax: Optional[float] = None      # 税率比例（0.15 = 15%）
    occupancy_max: Optional[int] = None  # 最多入住人数


def normalize_policy(raw: "RawHotel") -> HotelPolicy:
    """从 extra + 房型文本解析政策（P9）。

    未知一律 UNKNOWN（RULE 5：不猜 included/refundable）。
    优先级：extra 结构化字段 > 房型文本关键词。
    """
    extra = raw.extra or {}
    name = (raw.room_name or "").lower()

    # ---- breakfast ----
    breakfast = "UNKNOWN"
    b = str(extra.get("breakfast", "")).lower()
    if b in ("included", "true", "含早", "yes"):
        breakfast = "included"
    elif b in ("not_included", "false", "no", "不含早"):
        breakfast = "not_included"
    elif any(k in name for k in ("breakfast", "含早", "早餐")):
        breakfast = "included"

    # ---- cancellation ----
    cancellation = "UNKNOWN"
    c = str(extra.get("cancellation", "")).lower()
    import re as _re
    m_free = _re.search(r"free_before_(\d+)h", c)
    if m_free:
        cancellation = f"free_before_{m_free.group(1)}h"
    elif "free" in c or "免费取消" in c or "free cancellation" in name:
        cancellation = "free"
    elif "non_refundable" in c or "不可取消" in c or "non-refundable" in name:
        cancellation = "non_refundable"

    # ---- tax ----
    tax: Optional[float] = None
    t = extra.get("tax")
    if isinstance(t, (int, float)):
        tax = float(t)
    elif isinstance(t, str):
        try:
            tax = float(t)
        except ValueError:
            tax = None

    # ---- occupancy ----
    occ = extra.get("occupancy")
    if isinstance(occ, dict):
        tax_occ = occ.get("max_guests") or occ.get("max")
        tax_occ = int(tax_occ) if isinstance(tax_occ, (int, float)) else None
    elif isinstance(occ, (int, float)):
        tax_occ = int(occ)
    else:
        tax_occ = None

    return HotelPolicy(breakfast=breakfast, cancellation=cancellation,
                       tax=tax, occupancy_max=tax_occ)


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
