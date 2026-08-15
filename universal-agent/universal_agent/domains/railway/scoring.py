"""Railway Domain（P23）— 火车票确定性评分（RULE-005 程序化）。

维度（0-100）：
- 余票可得性 40 分：有票/余票>0 → 高分；售罄 → 低分
- 出发时段 30 分：早班（06-10）与常规班次较优
- 历时 20 分：越短越高
- 票价 10 分：越低越高（12306 票价 best-effort，未知时给中性分）

不引入 LLM（RULE-005）。PARTIAL（票价未知）可进 Preliminary，
不得直接作 Final 决定性依据（FR-073 同精神）。
"""
from __future__ import annotations

import logging
from typing import Dict

from ...core.contracts import RawRailway

log = logging.getLogger("ua.domains.railway.scoring")

#: 余票字段中视为"有票"的值（'有' / 数字>0 / 'B4'/'H3' 等票码）
_AVAILABLE_FLAGS = {"有", "是", "B", "H", "K", "L", "M", "N", "P", "Q"}


def _available(raw: RawRailway) -> int:
    """余票可得性分（0-40）。raw.extra 由 12306 源写入 available。"""
    avail = str(raw.extra.get("available", "")).strip()
    if not avail or avail in ("无", "0"):
        return 0
    if avail in ("有", "是"):
        return 40
    if avail.isdigit():
        n = int(avail)
        return 40 if n >= 1 else 0
    # 'B4'/'H3' 等 12306 票码 → 视为有票（部分有）
    if avail and avail[0] in _AVAILABLE_FLAGS:
        return 36
    return 20  # 未知 → 中性（fail-closed 不脑补满分）


def _time_score(depart_time: str) -> int:
    """出发时段分（0-30）：06-10 早班最受欢迎。"""
    try:
        hh = int(str(depart_time).split(":")[0])
    except (ValueError, IndexError):
        return 15
    if 6 <= hh < 10:
        return 30
    if 10 <= hh < 15:
        return 24
    if 15 <= hh < 20:
        return 18
    return 12  # 深夜/凌晨


def _duration_score(duration: str) -> int:
    """历时分（0-20）：越短越高。"""
    try:
        parts = str(duration).split(":")
        mins = int(parts[0]) * 60 + int(parts[1])
    except (ValueError, IndexError):
        return 10
    if mins <= 60:
        return 20
    if mins <= 120:
        return 16
    if mins <= 240:
        return 12
    return 8


def _price_score(price_cny: float, market_min: float) -> int:
    """票价分（0-10）：越低越高；未知/0 → 中性 5 分。"""
    if price_cny <= 0:
        return 5  # 票价未知（fail-closed 中性）
    if market_min <= 0:
        return 10
    ratio = market_min / price_cny
    return min(10, int(ratio * 10) + 1)


def score_railway(raw: RawRailway, market_min: float = 0.0) -> Dict[str, float]:
    """确定性评分 → {available, schedule, duration, price, total}。"""
    components = {
        "available": float(_available(raw)),
        "schedule": float(_time_score(raw.depart_time)),
        "duration": float(_duration_score(raw.arrive_time and _duration(raw))),
        "price": float(_price_score(raw.price_cny, market_min)),
    }
    components["total"] = sum(components.values())
    return components


def _duration(raw: RawRailway) -> str:
    """历时（HH:MM）—— 源未给时用到达-出发近似。"""
    if raw.extra.get("duration"):
        return str(raw.extra["duration"])
    try:
        h0, m0 = raw.depart_time.split(":"), raw.arrive_time.split(":")
        d = (int(h0[0]) * 60 + int(h0[1])) - (int(m0[0]) * 60 + int(m0[1]))
        d = abs(d)
        return f"{d // 60}:{d % 60:02d}"
    except (ValueError, AttributeError, IndexError):
        return "1:00"
