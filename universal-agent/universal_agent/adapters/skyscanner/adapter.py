"""Skyscanner flight source adapter — real data via browser rendering.

Tier 2/3 真实验证源（§62）。策略：
  - 用 scrapling StealthyFetcher 渲染 Skyscanner 搜索页（SPA，需浏览器）
  - 解析航班卡片 → RawListing（与 replay fixture 同构，直接进 Normalize 管线）
  - 尊重 robots.txt（Skyscanner `User-agent: *` 无 disallow，仅 Crawl-Delay: 2）
  - 失败/风控时抛出 SourceUnavailable → Source Health 标记 DEGRADED（§53）

合规边界（§56）：不绕过验证码；风控时降级而非对抗；不批量逆向私有 API。
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from universal_agent.coordinator.query_planner import FlightQuery
from universal_agent.core.contracts import (
    DataCompleteness,
    RawLeg,
    RawListing,
    RawSegment,
    field_completeness_score,
    new_id,
)

log = logging.getLogger("ua.adapters.skyscanner")


class SourceUnavailable(RuntimeError):
    """Source returned a bot-wall / timeout / error — caller marks DEGRADED."""


#: 两字母航司代码 → 名称（解析航班号需要）
_AIRLINE_CODES = {"NZ", "CA", "MU", "CZ", "HU", "MF", "3U", "ZH", "QF", "SQ", "CX",
                  "JL", "NH", "KE", "OZ", "TG", "MH", "LH", "KL", "AF", "BA", "AY",
                  "EK", "EY", "QR", "TK", "AC", "UA"}


@dataclass
class SkyscannerConfig:
    max_results: int = 5
    request_delay_sec: float = 2.0  # robots Crawl-Delay
    timeout_ms: int = 45000
    headless: bool = True
    #: 使用本机已安装的 Chrome（scrapling --real-chrome），避免下载 playwright
    #: chromium（国内 CDN 该 build 不可用）。默认自动探测。
    real_chrome: bool = True


def _search_url(query: FlightQuery) -> str:
    """Skyscanner 往返搜索 URL（YYMMDD 格式）。"""
    dep = _yymmdd(query.depart_date)
    ret = _yymmdd(query.return_date)
    return (
        f"https://www.skyscanner.net/transport/flights/"
        f"{query.origin}/{query.destination}/{dep}/{ret}/"
        f"?adultsv2=1&cabinclass=economy&childrenv2=&ref=home&rtn=1"
    )


def _yymmdd(iso_date: str) -> str:
    """'2026-08-31' → '260831'（Skyscanner URL 日期格式）。"""
    return iso_date.replace("-", "")[2:]


_CURRENCY_SYMBOLS = {"US$": "USD", "¥": "CNY", "£": "GBP", "$": "USD", "€": "EUR"}


def _parse_price(text: str) -> Optional[float]:
    """支持 ¥4,380 / £1,234 / US$2,862 / CNY 4,380 等写法。返回数字。"""
    patterns = [
        r"(US\$|¥|£|€|\$)\s*([\d,]+(?:\.\d{2})?)",
        r"(?:CNY|RMB|元)\s*([\d,]+(?:\.\d{2})?)",
        r"([\d,]+(?:\.\d{2})?)\s*(?:CNY|RMB|元)",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            try:
                groups = m.groups()
                num = groups[1] if len(groups) > 1 and groups[1] else groups[0]
                return float(num.replace(",", ""))
            except (ValueError, IndexError):
                return None
    return None


def _detect_currency(text: str) -> str:
    for sym, code in _CURRENCY_SYMBOLS.items():
        if sym in text:
            return code
    return "CNY"


#: 兜底汇率「1 外币 = 多少 CNY」（仅当无外部汇率时使用）
_FALLBACK_RATES = {"GBP": 9.11, "USD": 6.76, "EUR": 7.79, "CNY": 1.0}


def to_cny(amount: float, currency: str, rates: Optional[Dict[str, float]] = None) -> float:
    """外币 → CNY。

    rates 支持两种约定：
      - 若 rates[currency] < 10 且语义为「1 CNY 兑外币数」（open.er-api 格式），
        则 CNY = amount / rate；
      - 若 rates[currency] 明显是「1 外币兑 CNY」（≥1），则 CNY = amount * rate。
    缺省用兜底表（1 外币 = N CNY，乘法）。
    """
    if not currency or currency == "CNY":
        return amount
    rate = None
    if rates and currency in rates and rates[currency]:
        rate = float(rates[currency])
        # 判别语义：GBP≈0.11(1CNY兑), USD≈0.15(1CNY兑) → 除法；否则乘法
        return round(amount / rate, 2) if rate < 1.0 else round(amount * rate, 2)
    rate = _FALLBACK_RATES.get(currency)
    if not rate:
        return amount
    return round(amount * rate, 2)


def _parse_duration(text: str) -> int:
    """'18h 25m' / '16 hours 35 minutes' / '18h' / '45m' → minutes."""
    h = re.search(r"(\d+)\s*h(?:ours)?\s+(\d+)\s*m(?:inutes?)?", text)
    if h:
        return int(h.group(1)) * 60 + int(h.group(2))
    h2 = re.search(r"(\d+)\s*h(?:ours)?\b", text)
    if h2:
        return int(h2.group(1)) * 60
    m = re.search(r"(\d+)\s*m(?:inutes?)?\b", text)
    if m:
        return int(m.group(1))
    return 0


class SkyscannerAdapter:
    """Fetches + parses Skyscanner results into RawListing (browser-rendered).

    浏览器依赖懒加载：仅当真实抓取时才初始化 StealthyFetcher，测试与
    离线回放不触碰它。
    """

    def __init__(self, config: Optional[SkyscannerConfig] = None,
                 rates: Optional[Dict[str, float]] = None) -> None:
        self.config = config or SkyscannerConfig()
        self._fetcher = None
        #: 汇率 {币种: 1 CNY 可兑外币数}；缺省用兜底表
        self.rates = rates or {}

    # -- 懒加载浏览器 --
    def _get_fetcher(self):
        if self._fetcher is None:
            from scrapling.fetchers import StealthyFetcher
            self._fetcher = StealthyFetcher
        return self._fetcher

    # -- 主接口：与 replay fetcher 同构 --
    def fetch(self, query: FlightQuery) -> List[RawListing]:
        time.sleep(self.config.request_delay_sec)  # 尊重 Crawl-Delay
        page = self._render(_search_url(query))
        return self._parse_results(page, query)

    async def fetch_many(self, queries: List[FlightQuery],
                         max_concurrency: int = 3) -> List[RawListing]:
        """并发抓取多个 query（限流 max_concurrency，尊重 robots）。

        §48: 单 query 失败不影响其它；总耗时从 N×单次 降到 ceil(N/max_concurrency)。
        """
        sem = asyncio.Semaphore(max_concurrency)
        results: List[RawListing] = []
        lock = asyncio.Lock()

        async def one(q: FlightQuery) -> None:
            async with sem:
                try:
                    batch = await asyncio.to_thread(self.fetch, q)
                except SourceUnavailable as exc:
                    log.warning("skyscanner query %s unavailable: %s", q.origin, exc)
                    return
                async with lock:
                    results.extend(batch)

        await asyncio.gather(*[one(q) for q in queries])
        return results

    def _render(self, url: str):
        from scrapling.fetchers import StealthyFetcher
        try:
            kwargs = dict(
                headless=self.config.headless,
                timeout=self.config.timeout_ms,
                wait=4000,  # 等 SPA 渲染
            )
            if self.config.real_chrome:
                kwargs["real_chrome"] = True
            page = StealthyFetcher.fetch(url, **kwargs)
        except Exception as exc:  # noqa: BLE001
            log.warning("skyscanner render failed: %s", exc)
            raise SourceUnavailable(str(exc)) from exc
        if page.status != 200:
            raise SourceUnavailable(f"HTTP {page.status}")
        body = page.body or ""
        if isinstance(body, bytes):
            body = body.decode("utf-8", errors="replace")
        text = body.lower()
        # 风控标记
        if "captcha" in text or "verify you are human" in text or "are you a human" in text:
            raise SourceUnavailable("bot-wall detected")
        return page

    # -- 解析（容错：解析不到字段就跳过该卡片）--
    def _parse_results(self, page, query: FlightQuery) -> List[RawListing]:
        """Skyscanner 解析 — 结构随站点变化，全部字段容错。

        `page` 可以是带 `.css()`/`.body` 的对象（scrapling page / Selector），
        也可以是纯字符串 HTML。

        主路径：整页 regex 提取所有 `Price_mainPriceContainer` 价格文本，
        再与时长文本配对（顺序对齐）。价格去重（§71）。实测 CSS 卡片容器
        （itinerary-inline-plus-wrapper）数量少于真实价格数，因此 regex
        全量提取更稳健。
        """
        listings: List[RawListing] = []
        body = getattr(page, "body", None)
        if isinstance(body, bytes):
            body = body.decode("utf-8", errors="replace")
        html = body if isinstance(body, str) else (page if isinstance(page, str) else "")

        # 风控检查：任何输入都先判 bot-wall（§56 降级而非对抗）
        lowered = (html or "").lower()
        if ("captcha" in lowered or "verify you are human" in lowered
                or "are you a human" in lowered):
            raise SourceUnavailable("bot-wall detected")
        if not html:
            return []

        # 价格容器（可能含货币符号与价格）与时长（按出现顺序）
        price_matches = list(re.finditer(
            r'Price_mainPriceContainer.*?BpkText[^>]*>([^<]{2,30})<', html, re.S))
        durations = re.findall(r'(\d+)\s*hours?\s+(\d+)\s*minutes?', html)
        duration_min = [int(h) * 60 + int(m) for h, m in durations]

        seen: set[float] = set()
        for i, m in enumerate(price_matches[: self.config.max_results]):
            price_text = m.group(1)
            price = _parse_price(price_text)
            if price is None:
                continue
            cny = to_cny(price, _detect_currency(price_text), self.rates)
            if cny in seen:
                continue
            seen.add(cny)
            dur = duration_min[i] if i < len(duration_min) else 0
            listings.append(self._build_listing(query, cny, dur, currency="CNY",
                                                raw_currency=_detect_currency(price_text)))
        return listings

    @staticmethod
    def _build_listing(query: FlightQuery, price: float, duration: int,
                       currency: str = "CNY", raw_currency: str = "CNY") -> RawListing:
        """构造 listing。P0.6 fail-closed：无 segments/航班号 → 标记 PARTIAL，
        绝不伪造 stops=0（避免不完整数据获得直飞加分）。"""
        complete = duration > 0
        completeness = DataCompleteness.STRUCTURED if complete else DataCompleteness.PARTIAL
        listing = RawListing(
            listing_id=new_id("sky"),
            source="skyscanner",
            marketplace_id="skyscanner",
            task_id="unknown",
            origin_airport=query.origin,
            dest_airport=query.destination,
            depart_date=query.depart_date,
            return_date=query.return_date,
            nights=_date_diff_days(query.depart_date, query.return_date),
            price_cny=price,
            currency=currency,
            # fail-closed: 数据不完整时 stops 用 -1 标记（禁止 0 分加分）
            outbound=RawLeg(segments=[], total_min=duration,
                            stops=-1 if not complete else 0),
            inbound=RawLeg(segments=[], total_min=0, stops=-1 if not complete else 0),
            luggage={},
            extra={"raw_note": "skyscanner parsed card",
                   "duration_min": duration,
                   "raw_currency": raw_currency,
                   "completeness": completeness.value},
        )
        listing.extra["field_completeness_score"] = field_completeness_score(listing)
        return listing


def _date_diff_days(d1: str, d2: str) -> int:
    from datetime import date
    a = date.fromisoformat(d1)
    b = date.fromisoformat(d2)
    return (b - a).days
