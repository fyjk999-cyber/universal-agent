"""Hotel scoring — deterministic 0-100 (§32 RULE 7).

Dimensions: price (vs market min), rating (0-5), room grade.
"""
from __future__ import annotations

from typing import Dict

from ...core.contracts import RawHotel
from .knowledge import normalize_room, score_room

#: 各房型等级的目标分（standard=60 / superior=75 / deluxe=90 / suite=100）
_GRADE_TARGET = {"standard": 60.0, "superior": 75.0, "deluxe": 90.0, "suite": 100.0}


def _grade_score(raw: RawHotel) -> float:
    grade = normalize_room(raw.room_name).room_grade
    return _GRADE_TARGET.get(grade, 60.0)


def score_hotel(raw: RawHotel, market_min: float) -> Dict[str, float]:
    """Return {'total': ..., 'components': {...}}."""
    if market_min <= 0:
        price = 50.0
    else:
        ratio = raw.price_per_night_cny / market_min
        price = 100.0 if ratio <= 1.0 else max(20.0, 100 - (ratio - 1.0) * 50)

    rating = min(100.0, (raw.rating or 0.0) / 5.0 * 100)
    grade = _grade_score(raw)

    total = price * 0.5 + rating * 0.35 + grade * 0.15
    return {
        "total": round(total, 1),
        "components": {"price": round(price, 1), "rating": round(rating, 1),
                       "grade": round(grade, 1)},
    }
