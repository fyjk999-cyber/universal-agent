"""性价比评分（0~100）与 Top5 挑选。

评分维度（对应任务规格）：
  - 价格分：相对本次扫描市场最低价
  - 直飞加分
  - 转机时长合理度（理想 1.5~4h，可接受 1~6h）
  - 总旅行时间
  - 航司/行李/时段/衔接风险（质量分）
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from .models import Itinerary

log = logging.getLogger("flights_zqn.scoring")

# 常见国际大航司（用于质量分的小幅加分）
RELIABLE_AIRLINES = {
    "CA", "MU", "CZ", "HU", "MF", "3U", "ZH",  # 中国航司
    "NZ", "QF", "SQ", "CX", "KA", "JL", "NH", "KE", "OZ", "TG", "MH",
    "LH", "KL", "AF", "BA", "AY", "EK", "EY", "QR", "TK", "AC", "UA",
}

UNRELIABLE_AIRLINES: set = set()  # 如需标记可扩展


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _price_score(price: float, market_min: float) -> float:
    """价格分 0~100：相对最低价。最低价=100；高出 60% 以上快速衰减。"""
    if market_min <= 0:
        return 50.0
    ratio = price / market_min
    if ratio <= 1.0:
        return 100.0
    # 高 10% 内线性下降到 85；之后继续下降，高 60% 时约 40
    if ratio <= 1.10:
        return 100 - (ratio - 1.0) / 0.10 * 15
    if ratio <= 1.60:
        return 85 - (ratio - 1.10) / 0.50 * 45
    return 40 - (ratio - 1.60) / 1.0 * 20


def _layover_score(leg, cfg: Dict) -> float:
    """单段转机时长合理度 0~100（取该方向最差的一次转机）。"""
    ideal_min, ideal_max = cfg["layover_ideal_min"], cfg["layover_ideal_max"]
    accept_min, accept_max = cfg["layover_accept_min"], cfg["layover_accept_max"]
    worst = 0.0
    for lay in leg.layovers or [0]:
        if lay == 0:
            worst = max(worst, 100.0)
            continue
        if ideal_min <= lay <= ideal_max:
            s = 100.0
        elif accept_min <= lay < ideal_min or ideal_max < lay <= accept_max:
            # 边缘区间线性衰减
            if lay < ideal_min:
                s = 100 - (ideal_min - lay) / (ideal_min - accept_min) * 40
            else:
                s = 100 - (lay - ideal_max) / (accept_max - ideal_max) * 40
        else:
            s = 30.0 if lay <= 8 * 60 else 10.0  # >8h 很差
        if leg.overnight_layover:
            s = min(s, 25.0)
        if leg.airport_change:
            s = min(s, 15.0)
        if leg.self_transfer:
            s = min(s, 5.0)
        worst = s if worst == 0.0 else min(worst, s)  # 取最差的一次转机
    return worst


def _total_time_score(it: Itinerary) -> float:
    """总旅行时间 0~100：往返总时长，越短越好。"""
    total_h = it.total_duration_min / 60.0
    if total_h <= 20:
        return 100.0
    if total_h <= 30:
        return 100 - (total_h - 20) / 10 * 25
    if total_h <= 45:
        return 75 - (total_h - 30) / 15 * 35
    return 40 - (total_h - 45) / 15 * 20


def _quality_score(it: Itinerary) -> float:
    """航司/行李/时段/衔接风险质量分 0~100。"""
    score = 70.0
    # 航司
    for a in it.airlines:
        if a in RELIABLE_AIRLINES:
            score += 6
            break
    if any(a in UNRELIABLE_AIRLINES for a in it.airlines):
        score -= 20
    # 行李信息是否明确
    if it.luggage.get("checked") not in (None, "", "0", "0kg", "不含"):
        score += 4
    else:
        score -= 6  # 信息缺失或不含托运
    # 时段合理性：去程首段出发 6:00~22:00 合理；抵达 ZQN 时段
    out_first = it.outbound.first
    if out_first:
        try:
            h = int(out_first.dep_time.split(":")[0])
            if 6 <= h <= 22:
                score += 3
            else:
                score -= 5
        except (ValueError, AttributeError):
            pass
    # 衔接风险
    if it.outbound.self_transfer or it.inbound.self_transfer:
        score -= 25
    if it.outbound.airport_change or it.inbound.airport_change:
        score -= 15
    if it.outbound.overnight_layover or it.inbound.overnight_layover:
        score -= 20
    # 是否直飞
    if it.is_direct:
        score += 10
    return clamp(score, 0, 100)


def score_itinerary(it: Itinerary, market_min: float, cfg: Dict) -> float:
    """综合评分 0~100。"""
    w = cfg["scoring"]
    p = _price_score(it.price_cny, market_min)
    stops_bonus = 100.0 if it.is_direct else (60.0 if it.outbound.stops + it.inbound.stops == 1 else 20.0)
    lay = (_layover_score(it.outbound, w) + _layover_score(it.inbound, w)) / 2
    tt = _total_time_score(it)
    q = _quality_score(it)
    total = (
        p * w["price_weight"] + stops_bonus * w["stops_bonus"] + lay * w["layover_score"]
        + tt * w["total_time_score"] + q * w["quality_score"]
    ) / 100.0
    it.score = round(total, 1)
    it.score_breakdown = {"price": round(p, 1), "stops": round(stops_bonus, 1),
                          "layover": round(lay, 1), "total_time": round(tt, 1), "quality": round(q, 1)}
    return it.score


def filter_and_score(itineraries: List[Itinerary], cfg: Dict) -> List[Itinerary]:
    """先过滤不合格方案，再评分。返回（评分排序后的）候选。"""
    filters = cfg["filters"]
    kept = []
    prices = [it.price_cny for it in itineraries if it.price_cny and it.price_cny > 0]
    market_min = min(prices) if prices else 0.0
    for it in itineraries:
        stops = it.outbound.stops + it.inbound.stops
        if stops > filters["max_stops"]:
            continue
        if it.outbound.self_transfer or it.inbound.self_transfer:
            if not filters["allow_self_transfer"]:
                it.notes.append("自行转机（Self-transfer），风险高，默认排除")
                continue
        if it.outbound.airport_change or it.inbound.airport_change:
            if not filters["allow_airport_change"]:
                it.notes.append("需更换机场转机，默认排除")
                continue
        # 超长转机
        for leg_name, leg in (("去程", it.outbound), ("返程", it.inbound)):
            for lay in leg.layovers or []:
                if lay > filters["max_layover_min"]:
                    it.notes.append(f"{leg_name}转机 {lay // 60}h{lay % 60:02d}m 过长，仅当价格极优才考虑")
        # 单程超长
        for leg_name, leg in (("去程", it.outbound), ("返程", it.inbound)):
            if leg.total_min > filters["max_total_hours"] * 60:
                it.notes.append(f"{leg_name}总时长 {(leg.total_min // 60)}h 过长")
        # 异常低价标记（不排除，但单独标注待校验）
        if market_min and it.price_cny < market_min * (1 - filters["price_ratio_to_reject"]):
            it.notes.append("⚠ 明显低于市场价，需校验价格真实性")
        score_itinerary(it, market_min, cfg)
        kept.append(it)
    kept.sort(key=lambda x: x.score, reverse=True)
    return kept


def pick_top5(scored: List[Itinerary], cfg: Dict, top_n: int = 5) -> List[Itinerary]:
    """综合挑选 Top5，兼顾差异性与代表性：
    最低价 / 最高性价比 / 最短旅行时间 / 最佳上海 / 最佳杭州。
    """
    if not scored:
        return []
    picks: List[Itinerary] = []

    def add(it: Optional[Itinerary]) -> None:
        if it and all(it is not p for p in picks):
            picks.append(it)

    # 1) 最高分（综合最佳）
    add(scored[0])
    # 2) 最低价
    add(min(scored, key=lambda x: (x.price_cny, -x.score)))
    # 3) 最短总旅行时间
    add(min(scored, key=lambda x: (x.total_duration_min, -x.score)))
    # 4) 最佳上海（PVG/SHA）
    sh = [x for x in scored if x.origin_airport in ("PVG", "SHA") and all(x is not p for p in picks)]
    if sh:
        add(max(sh, key=lambda x: x.score))
    # 5) 最佳杭州
    hz = [x for x in scored if x.origin_airport == "HGH" and all(x is not p for p in picks)]
    if hz:
        add(max(hz, key=lambda x: x.score))
    # 若仍不足 top_n，按分数补齐（跳过重复）
    for it in scored:
        if len(picks) >= top_n:
            break
        add(it)
    # 若某一端城市明显无竞争力（没有任何推荐），不强凑 —— 保持现状
    return picks[:top_n]
