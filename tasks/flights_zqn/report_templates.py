"""皇后镇机票扫描报告渲染（严格遵循任务规格输出格式）。"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List

from .models import Itinerary
from .scoring import pick_top5

log = logging.getLogger("flights_zqn.report")

MEDALS = ["🥇 推荐 1", "🥈 推荐 2", "🥉 推荐 3", "推荐 4", "推荐 5"]
TITLES = ["最佳综合选择", "最低价方案", "最短旅行时间", "最佳上海出发", "最佳杭州出发"]


def _fmt_price(v) -> str:
    try:
        return f"¥{round(float(v)):,}"
    except (TypeError, ValueError):
        return "—"


def _fmt_dur(minutes) -> str:
    if not minutes:
        return "—"
    h, m = divmod(int(minutes), 60)
    return f"{h}小时{m:02d}分"


def _fmt_layover(minutes) -> str:
    if not minutes:
        return "—"
    h, m = divmod(int(minutes), 60)
    return f"{h}小时{m:02d}分"


def _fmt_date(d: str) -> str:
    try:
        dt = datetime.strptime(d, "%Y-%m-%d")
        return f"{dt.year}年{dt.month}月{dt.day}日"
    except (ValueError, TypeError):
        return d or "—"


def _leg_block(leg) -> str:
    """渲染去程/返程详情。"""
    lines = []
    for i, seg in enumerate(leg.segments):
        arrow = "直飞" if len(leg.segments) == 1 else ("转机" if i < len(leg.segments) - 1 else "到达")
        if i == 0:
            lines.append(f"{seg.dep_airport} {seg.dep_time}")
        else:
            lines.append(f"→ 转机机场 {leg.layover_airports[i-1]}")
            lines.append(f"转机 {_fmt_layover(leg.layovers[i-1])}")
            lines.append(f"→ {seg.dep_airport} {seg.dep_time}")
        lines.append(f"→ {seg.arr_airport} {seg.arr_time} ({seg.airline}{seg.flight_no})")
    return "\n".join(lines)


def _score_label(score) -> str:
    try:
        s = float(score)
    except (TypeError, ValueError):
        return "—"
    if s >= 90:
        return "非常值得购买"
    if s >= 80:
        return "值得购买"
    if s >= 70:
        return "可以考虑"
    if s >= 60:
        return "一般"
    return "原则上不建议"


def _luggage_str(it: Itinerary) -> str:
    carry = it.luggage.get("carry_on", "—")
    checked = it.luggage.get("checked", "—")
    return f"手提：{carry}\n托运：{checked}"


def render_one(it: Itinerary, idx: int) -> str:
    """渲染单个推荐方案。"""
    title = TITLES[idx] if idx < len(TITLES) else "综合推荐"
    out = it.outbound
    inn = it.inbound
    r = []
    r.append(f"## {MEDALS[idx]}｜{title}\n")
    r.append("路线：")
    r.append(f"{it.origin_airport} → {it.dest_airport}（出发）")
    r.append(f"{it.dest_airport} → {it.origin_airport}（返程）\n")
    r.append("日期：")
    r.append(f"去程：{_fmt_date(it.depart_date)}")
    r.append(f"返程：{_fmt_date(it.return_date)}\n")
    r.append(f"旅行天数：\n{it.nights + 1} 天 / {it.nights} 晚\n")
    r.append(f"航空公司：\n{it.airline_full or '、'.join(it.airlines) or '—'}\n")
    r.append("航班号：")
    fns = []
    for seg in out.segments + inn.segments:
        fns.append(f"{seg.airline}{seg.flight_no}")
    r.append(" / ".join(fns) + "\n")
    r.append("去程：")
    r.append(_leg_block(out))
    r.append("")
    r.append(f"去程总时间：\n{_fmt_dur(out.total_min)}\n")
    r.append("返程：")
    r.append(_leg_block(inn))
    r.append("")
    r.append(f"返程总时间：\n{_fmt_dur(inn.total_min)}\n")
    r.append(f"转机：\n{out.stops + inn.stops} 次\n")
    r.append("行李：")
    r.append(_luggage_str(it))
    r.append("")
    r.append("往返含税：")
    r.append(f"**{_fmt_price(it.price_cny)} / 人**\n")
    fx_note = ""
    if it.price_orig is not None and it.currency_orig != "CNY":
        fx_note = f"（原始价格 {it.currency_orig} {it.price_orig:,.0f}，按汇率换算为人民币；{it.fx_note}）"
    r.append(f"预订渠道：\n{it.booking_channel or it.source or '—'}{fx_note}\n")
    r.append("性价比评分：")
    r.append(f"**{it.score} / 100**（{_score_label(it.score)}）\n")
    r.append("推荐理由：")
    # notes 是 List[str]（模型定义），不是 dict；从中提取"异常低价"等备注或给默认理由
    note_txt = "；".join(it.notes[:2]) if it.notes else "价格与行程综合表现优秀。"
    r.append(note_txt)
    r.append("")
    r.append("注意事项：")
    r.append("请以预订页面最终价格与行李政策为准。")
    r.append("")
    r.append("预订链接：")
    r.append(it.link or "（搜索页可继续查询；请直接前往平台核对价格）")
    r.append("")
    r.append("---")
    r.append("")
    return "\n".join(r)


def build_report(result: Dict[str, Any]) -> str:
    """根据扫描结果字典生成完整 Markdown 报告。"""
    R: List[str] = []
    R.append("## ✈️ 皇后镇机票扫描报告\n")
    R.append(f"扫描时间：\n{result.get('scan_time', '—')}\n")
    R.append(f"目前最低往返价格：\n{_fmt_price(result.get('min_price'))} / 人\n")
    prev = result.get("prev_price")
    if prev is not None:
        delta = (result.get("min_price") or 0) - prev
        if abs(delta) < 1:
            R.append("相比上一次扫描：\n价格基本不变\n")
        else:
            arrow = "↓" if delta < 0 else "↑"
            R.append(f"相比上一次扫描：\n{arrow} ¥{abs(round(delta)):,}\n")
    else:
        R.append("相比上一次扫描：\n（首次扫描，暂无对比）\n")
    R.append("---")
    R.append("")

    # 重要价格变化置顶
    if result.get("alerts"):
        R.append("## 🔔 重要价格变化\n")
        for a in result["alerts"]:
            R.append(f"- {a}")
        R.append("")
        R.append("---")
        R.append("")

    # 异常低价检查
    if result.get("abnormal_low"):
        R.append("## ⚠️ 异常低价检查\n")
        for a in result["abnormal_low"]:
            R.append(f"- {a}")
        R.append("")
        R.append("---")
        R.append("")

    # Top 5
    top5 = result.get("top5", [])
    if not top5:
        R.append("本次扫描未获得有效方案。请稍后重试或检查数据源可用性。\n")
    else:
        R.append(f"本次共扫描 {result.get('query_count', 0)} 组日期组合，得到 {result.get('candidate_count', 0)} 个候选方案。\n")
        R.append("---")
        R.append("")
        for idx, it in enumerate(top5):
            R.append(render_one(it, idx))

    # 购买建议
    R.append("## 💡 本次购买建议\n")
    advice = result.get("advice", {})
    R.append(f"1. **当前最低价**：{_fmt_price(advice.get('min_price'))} / 人"
             f"（{advice.get('min_price_desc', '')}）")
    R.append(f"2. **当前最值得买**：{advice.get('best_desc', '—')}")
    R.append(f"3. **杭州 / 上海整体对比**：{advice.get('city_compare', '—')}")
    R.append(f"4. **省钱的代价**：{advice.get('tradeoff', '—')}")
    level = advice.get("price_level", "—")
    R.append(f"5. **当前价格属于**：{level}")
    R.append(f"6. **综合建议**：{advice.get('action', '继续观察')}\n")
    R.append("> 说明：建议结合航班质量判断，不单纯依据价格。\n")

    # 历史价格追踪
    R.append("## 📈 历史价格追踪\n")
    R.append("| 扫描时间 | 最低价(CNY/人) | 较上次 | 备注 |")
    R.append("|---|---|---|---|")
    for h in result.get("history_table", []):
        R.append(f"| {h['ts']} | {_fmt_price(h['price'])} | {h.get('delta', '—')} | {h.get('note', '')} |")
    R.append("")
    if result.get("is_hist_low"):
        R.append("🏆 **历史新低**：本次价格为历史扫描以来最低。\n")
    R.append("---")
    R.append("")
    R.append(f"*数据来源：{result.get('sources_desc', '—')}；价格均为含税往返总价（人民币/人）。"
             f"汇率查询时间：{result.get('fx_note', '—')}*")
    R.append("*价格实时变动，请以预订页面为准。*")
    return "\n".join(R)
