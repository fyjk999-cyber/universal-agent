"""flights_zqn 任务：杭州/上海 → 皇后镇(ZQN) 往返机票定期扫描。

通用框架下的第一个实例任务。任务实现只管“本任务”的业务逻辑：
  - 生成日期组合（出发窗口 × 返程偏移）
  - 调用数据源搜索
  - 过滤 + 性价比评分 + Top5
  - 价格提醒 / 历史对比
  - 渲染报告
"""
from __future__ import annotations

import datetime as dt
import logging
import os
from typing import Any, Dict, List, Optional

from scanner.core import ScanTask, TaskContext, now_str

from .models import Itinerary, Leg, Segment
from .report_templates import build_report
from .scoring import filter_and_score, pick_top5

log = logging.getLogger("flights_zqn")

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.yaml")


def _load_config() -> Dict[str, Any]:
    import yaml

    with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _date_range(start: str, end: str) -> List[str]:
    s = dt.date.fromisoformat(start)
    e = dt.date.fromisoformat(end)
    out = []
    d = s
    while d <= e:
        out.append(d.isoformat())
        d += dt.timedelta(days=1)
    return out


class FlightsZqnTask(ScanTask):
    name = "flights_zqn"
    schedule = "0 9,15,21 * * *"

    def describe(self) -> str:
        return "杭州/上海 → 皇后镇(ZQN) 往返机票扫描（2026-08-30~09-05 出发，6~8 晚）"

    # ---------- 数据源 ----------
    def _build_searchers(self):
        import importlib

        searchers = []
        cfg = self._cfg
        order = cfg["sources"]["preferred_order"]
        # 配置驱动的动态加载：缺模块/类时跳过并告警，不崩溃
        factory = {
            "bing": ("bing", "BingSearcher"),
            "qunar": ("qunar", "QunarSearcher"),
            "ctrip": ("ctrip", "CtripSearcher"),
        }
        for name in order:
            spec = factory.get(name)
            if not spec:
                log.warning("数据源 %s 未注册，跳过", name)
                continue
            mod_name, cls_name = spec
            try:
                mod = importlib.import_module(f".searchers.{mod_name}", __package__)
                cls = getattr(mod, cls_name, None)
                if cls is None:
                    log.warning("数据源 %s 缺少 %s 类，跳过", name, cls_name)
                    continue
                searchers.append(cls(cfg["sources"].get(name, {})))
            except Exception as exc:  # noqa: BLE001
                log.warning("初始化数据源 %s 失败: %s", name, exc)
        return searchers

    # ---------- 主流程 ----------
    def run(self, ctx: TaskContext) -> Dict[str, Any]:
        self._cfg = _load_config()
        cfg = self._cfg
        task_cfg = cfg["task"]
        origins = cfg["origins"]
        dest = cfg["dest"]["airport"]
        depart_dates = _date_range(cfg["dates"]["depart_start"], cfg["dates"]["depart_end"])
        offsets = cfg["dates"]["return_offsets"]
        adults = cfg["dates"]["adults"]

        # 生成所有日期组合
        combos = []
        for dep in depart_dates:
            for off in offsets:
                ret = (dt.date.fromisoformat(dep) + dt.timedelta(days=off)).isoformat()
                combos.append((dep, ret, off))
        log.info("共 %d 个出发日期 × %d 个返程偏移 = %d 组日期组合", len(depart_dates), len(offsets), len(combos))

        searchers = self._build_searchers()
        if not searchers:
            raise RuntimeError("没有可用数据源")

        from .searchers import SearcherPool

        pool = SearcherPool(searchers)
        pool.warmup_all()

        all_its: List[Itinerary] = []
        source_used = set()
        for origin in origins:
            code = origin["airport"]
            for dep, ret, off in combos:
                its, used = pool.search_roundtrip(code, dest, dep, ret, adults)
                source_used.update(used)
                for it in its:
                    it.origin_airport = code
                    it.nights = off
                all_its.extend(its)
                log.info("[%s] %s~%s (%d晚): %d 方案", code, dep, ret, off, len(its))
        pool.shutdown_all()

        log.info("共收集 %d 个原始方案", len(all_its))
        # 价格统一为 CNY
        for it in all_its:
            self._normalize_price(it, ctx)

        candidates = filter_and_score(all_its, cfg)
        log.info("过滤评分后候选 %d 个", len(candidates))

        top5 = pick_top5(candidates, cfg, top_n=5)
        min_price = min((it.price_cny for it in candidates if it.price_cny), default=None)

        # 历史对比
        history = ctx.history
        prev = history.last()
        prev_price = prev.get("summary", {}).get("min_price") if prev else None
        delta = None
        if prev_price and min_price is not None:
            try:
                delta = min_price - float(prev_price)
            except (TypeError, ValueError):
                delta = None
        lowest_ever = history.lowest_ever()
        is_hist_low = bool(
            lowest_ever and min_price is not None and min_price < lowest_ever["price"]
        ) or (lowest_ever is None and min_price is not None)

        alerts = self._build_alerts(min_price, prev_price, delta, is_hist_low, candidates, cfg)

        result = {
            "scan_time": now_str(),
            "min_price": min_price,
            "prev_price": prev_price,
            "query_count": len(origins) * len(combos),
            "candidate_count": len(candidates),
            "top5": top5,
            "alerts": alerts,
            "abnormal_low": self._abnormal_low_checks(candidates, cfg),
            "is_hist_low": is_hist_low,
            "sources_desc": "、".join(sorted(source_used)) if source_used else "无",
            "fx_note": f"{ctx.fx.source}（{ctx.fx.checked_at}）",
            "history_table": self._history_table(history),
            "advice": self._advice(min_price, top5, candidates, cfg),
        }
        result["report_md"] = build_report(result)
        return result

    # ---------- 价格归一化 ----------
    def _normalize_price(self, it: Itinerary, ctx: TaskContext) -> None:
        """把各数据源价格统一换算为 CNY（保留原始币种与换算说明）。"""
        if it.currency_orig == "CNY":
            it.fx_note = "数据源直接以 CNY 计价"
            return
        cny = ctx.fx.to_cny(it.price_cny, it.currency_orig) if it.price_cny else None
        if cny is not None:
            it.fx_note = f"原始 {it.currency_orig} {it.price_orig or it.price_cny:,.0f} 按汇率换算（{ctx.fx.checked_at}）"
            it.price_cny = cny

    # ---------- 提醒 ----------
    def _build_alerts(self, min_price, prev_price, delta, is_hist_low, candidates, cfg) -> List[str]:
        alerts: List[str] = []
        a_cfg = cfg["alerts"]
        if delta is not None and prev_price is not None:
            pct = abs(delta) / prev_price * 100 if prev_price else 0
            if delta <= -a_cfg["big_drop_cny"] or pct >= a_cfg["big_drop_pct"]:
                alerts.append(f"🚨 明显降价：最低价较上次下降 ¥{abs(round(delta)):,}"
                              f"（{-delta / prev_price * 100:.1f}%），建议重点考虑购买")
            elif delta <= -a_cfg["hot_drop_cny"]:
                alerts.append(f"🔥 值得关注：最低价较上次下降 ¥{abs(round(delta)):,}")
        if is_hist_low and min_price is not None:
            alerts.append(f"🏆 历史新低：当前最低价 ¥{round(min_price):,} 为扫描以来最低")
        # 优质方案大幅降价检测（在前 10 候选里找）
        if prev_price is not None and candidates:
            for it in candidates[:10]:
                pass  # 需要历史中有对应方案的记录，暂以最低价对比为主
        return alerts

    def _abnormal_low_checks(self, candidates, cfg) -> List[str]:
        """异常低价检查：比市场均价低 20%+ 的方案逐条说明。"""
        prices = sorted({it.price_cny for it in candidates if it.price_cny})
        if len(prices) < 3:
            return []
        import statistics

        median = statistics.median(prices)
        out = []
        for it in candidates:
            if it.price_cny and it.price_cny <= median * 0.8:
                detail = "；".join(it.notes[:3]) if it.notes else "无明显异常"
                out.append(
                    f"方案 {it.origin_airport} {it.depart_date}~{it.return_date} "
                    f"¥{round(it.price_cny):,} 低于市场中位价 ¥{round(median):,} 20%以上——{detail}"
                )
        return out

    def _history_table(self, history) -> List[Dict[str, Any]]:
        seq = history.price_history()
        out = []
        for i, item in enumerate(seq):
            delta = ""
            if i > 0:
                d = item["price"] - seq[i - 1]["price"]
                if abs(d) >= 1:
                    delta = ("↓" if d < 0 else "↑") + f" ¥{abs(round(d)):,}"
                else:
                    delta = "持平"
            note = ""
            if i == len(seq) - 1 and item["price"] == min(x["price"] for x in seq):
                note = "🏆 历史新低"
            out.append({"ts": item["ts"], "price": item["price"], "delta": delta, "note": note})
        return out

    def _advice(self, min_price, top5, candidates, cfg) -> Dict[str, Any]:
        """购买建议（规格第九节）。"""
        advice: Dict[str, Any] = {}
        best = top5[0] if top5 else None
        advice["min_price"] = min_price
        advice["min_price_desc"] = ""
        if min_price is not None:
            advice["min_price_desc"] = f"（{candidates[0].origin_airport} {candidates[0].depart_date}~{candidates[0].return_date}）" if candidates else ""
        advice["best_desc"] = ""
        if best:
            advice["best_desc"] = (
                f"{best.origin_airport} {best.depart_date}~{best.return_date} "
                f"{best.airline_full or '、'.join(best.airlines)} 往返 ¥{round(best.price_cny):,}"
                f"（评分 {best.score}）"
            )
        # 杭州 vs 上海
        sh = [it for it in candidates if it.origin_airport in ("PVG", "SHA") and it.score]
        hz = [it for it in candidates if it.origin_airport == "HGH" and it.score]
        if sh and hz:
            sh_best = max(sh, key=lambda x: x.score)
            hz_best = max(hz, key=lambda x: x.score)
            if sh_best.score - hz_best.score >= 3:
                advice["city_compare"] = f"上海更优：最佳方案 ¥{round(sh_best.price_cny):,}（{sh_best.score}分）vs 杭州 ¥{round(hz_best.price_cny):,}（{hz_best.score}分）"
            elif hz_best.score - sh_best.score >= 3:
                advice["city_compare"] = f"杭州更优：最佳方案 ¥{round(hz_best.price_cny):,}（{hz_best.score}分）vs 上海 ¥{round(sh_best.price_cny):,}（{sh_best.score}分）"
            else:
                advice["city_compare"] = "两地价格接近，按出行便利度选择"
        elif sh:
            advice["city_compare"] = "上海方案更有竞争力，杭州暂无可比方案"
        elif hz:
            advice["city_compare"] = "杭州方案更有竞争力，上海暂无可比方案"
        else:
            advice["city_compare"] = "暂无有效方案"

        # 省钱 vs 时间的代价
        if best and min_price and candidates:
            cheapest = min(candidates, key=lambda x: x.price_cny)
            if cheapest is not best and cheapest.price_cny < best.price_cny:
                extra_min = cheapest.total_duration_min - best.total_duration_min
                advice["tradeoff"] = (
                    f"最低价方案（¥{round(cheapest.price_cny):,}）比最佳方案（¥{round(best.price_cny):,}）"
                    f"省 ¥{round(best.price_cny - cheapest.price_cny):,}，但单程/总旅行时间约多 "
                    f"{extra_min // 60}h{extra_min % 60:02d}m"
                )
            else:
                advice["tradeoff"] = "最佳方案即最低价方案，无需为省钱牺牲时间"
        else:
            advice["tradeoff"] = "—"

        # 价格档位判断
        if min_price is not None:
            # 参考基准：此航线淡旺季。HGH/PVG→ZQN 往返常态约 4500~9000
            if min_price < 4000:
                level = "非常便宜"
            elif min_price < 5500:
                level = "比较便宜"
            elif min_price < 7500:
                level = "正常"
            elif min_price < 9500:
                level = "偏贵"
            else:
                level = "很贵"
            advice["price_level"] = level
            # 行动建议
            if level in ("非常便宜", "比较便宜") and best and best.score >= 80:
                advice["action"] = "立即购买"
            elif level in ("非常便宜", "比较便宜"):
                advice["action"] = "可以购买"
            elif level == "正常":
                advice["action"] = "可以购买"
            else:
                advice["action"] = "继续观察"
        else:
            advice["price_level"] = "—"
            advice["action"] = "继续观察"
        return advice

    # ---------- 报告 ----------
    def render_report(self, result: Dict[str, Any], ctx: TaskContext) -> str:
        return result.get("report_md") or build_report(result)

    # ---------- 测试 ----------
    def test_search(self, ctx: TaskContext, query: Optional[str] = None) -> None:
        """测试单个日期组合的搜索。"""
        self._cfg = _load_config()
        searchers = self._build_searchers()
        from .searchers import SearcherPool

        pool = SearcherPool(searchers)
        pool.warmup_all()
        origin = query or "HGH"
        its, used = pool.search_roundtrip(origin, "ZQN", "2026-08-30", "2026-09-06", 1)
        pool.shutdown_all()
        for it in its[:10]:
            print(f"{it.origin_airport} {it.depart_date}~{it.return_date} ¥{it.price_cny} "
                  f"{[s.flight_no for s in it.outbound.segments]} → {[s.flight_no for s in it.inbound.segments]}")
        print(f"共 {len(its)} 个方案，来源 {used}")


TASK = FlightsZqnTask()
