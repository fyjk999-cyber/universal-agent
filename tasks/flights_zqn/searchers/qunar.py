"""去哪儿（Qunar）国际机票数据源适配器。

原理：
  - 用 scrapling DynamicFetcher（headless Chrome）加载 qunar 国际机票搜索页；
    搜索参数直接放在 URL query（from/to/depdate/retdate）。
  - 页面加载后解析结果列表（.b_space / .space / 价格 .price / 时长 .time），
    提取 价格 / 时长 / 经停 等摘要，产出统一 Itinerary。
  - 价格单位 CNY（去哪儿国内计价），无需汇率换算。

注意事项：
  - 去哪儿对自动化有风控，失败率偏高；框架按 preferred_order 依次尝试，
    该源失败不影响整体（SearcherPool 捕获异常）。
  - 结果卡片结构与文案可能随站点改版变化，解析失败时返回空列表并告警。
"""
from __future__ import annotations

import logging
import re
from typing import List, Optional

from ..models import Itinerary, Leg, Segment
from . import FlightSearcher

log = logging.getLogger("flights_zqn.qunar")

QUNAR_URL = "https://flight.qunar.com/international/"

# 结果卡片常见选择器（改版时更新）
CARD_SELS = [
    ".b_space",
    ".space",
    "[class*='search-result'] [class*='item']",
    "[class*='result'] [class*='space']",
]
PRICE_RE = re.compile(r"¥\s?([\d,]+)")
PRICE_ALT_RE = re.compile(r"([\d,]+)\s*元")
DUR_RE = re.compile(r"(\d+)\s*小时\s*(\d+)?\s*分")
STOPS_RE = re.compile(r"经停\s*(\d+)\s*站")
TIME_RE = re.compile(r"(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})")


class QunarSearcher(FlightSearcher):
    name = "qunar"
    currency = "CNY"
    needs_browser = True

    def __init__(self, config: dict):
        self.config = config or {}
        self.base = self.config.get("base", QUNAR_URL)

    # ---------------- 搜索 ----------------
    def search_roundtrip(self, origin: str, dest: str, depart: str, return_: str,
                         adults: int = 1) -> List[Itinerary]:
        url = (
            f"{self.base}"
            f"?from={origin}&to={dest}"
            f"&depdate={depart}&retdate={return_}"
            f"&adult={adults}"
        )
        try:
            from scrapling.fetchers import DynamicFetcher

            page = DynamicFetcher.fetch(
                url, headless=True, network_idle=True, timeout=45000,
                real_chrome=True,  # 复用本机 Chrome，避免下载 playwright 浏览器
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("qunar 抓取失败 %s->%s %s~%s: %s", origin, dest, depart, return_, exc)
            return []

        text = page.html_content if hasattr(page, "html_content") else str(page)
        cards = self._extract_cards(page, text)
        out: List[Itinerary] = []
        seen = set()
        for card_text in cards[:30]:
            price = self._parse_price(card_text)
            if price is None or price <= 0:
                continue
            m_dur = DUR_RE.search(card_text)
            dur_min = self._to_min(m_dur.group(1), m_dur.group(2)) if m_dur else 0
            m_stops = STOPS_RE.search(card_text)
            stops = int(m_stops.group(1)) if m_stops else (0 if "直达" in card_text else 1)
            m_t = TIME_RE.search(card_text)
            dep_t = m_t.group(1) if m_t else ""
            arr_t = m_t.group(2) if m_t else ""

            k = (round(price), dur_min // 60, stops)
            if k in seen:
                continue
            seen.add(k)

            seg = Segment(
                airline="", flight_no="", dep_airport=origin, arr_airport=dest,
                dep_time=dep_t, arr_time=arr_t, dep_date=depart, arr_date=return_,
                duration_min=0,
            )
            outbound = Leg(segments=[seg], total_min=dur_min, stops=stops)
            inbound = Leg(segments=[], total_min=dur_min, stops=stops)
            out.append(Itinerary(
                origin_airport=origin, dest_airport=dest,
                depart_date=depart, return_date=return_, nights=0,
                outbound=outbound, inbound=inbound,
                price_cny=price, price_orig=price, currency_orig="CNY",
                booking_channel="去哪儿网 (Qunar)",
                source="qunar",
            ))
        log.info("qunar %s->%s %s~%s 解析 %d 个方案", origin, dest, depart, return_, len(out))
        return out

    def _extract_cards(self, page, text: str) -> List[str]:
        """从页面对象或 HTML 文本中提取结果卡片文本。"""
        # 优先用页面选择器；失败则退化为 HTML 片段切分
        for sel in CARD_SELS:
            try:
                nodes = page.css(sel) if hasattr(page, "css") else []
                if nodes:
                    return [(n.text() if hasattr(n, "text") else str(n)) for n in nodes]
            except Exception:  # noqa: BLE001
                continue
        # 退化：按价格出现切块
        parts = re.split(r"(?=¥\s?[\d,]+)", text)
        return [p for p in parts if "¥" in p and len(p) < 2000]

    @staticmethod
    def _parse_price(text: str) -> Optional[float]:
        m = PRICE_RE.search(text) or PRICE_ALT_RE.search(text)
        if m:
            try:
                return float(m.group(1).replace(",", ""))
            except ValueError:
                return None
        return None

    @staticmethod
    def _to_min(hours_str, mins_str) -> int:
        try:
            return int(hours_str) * 60 + int(mins_str or 0)
        except (ValueError, TypeError):
            return 0
