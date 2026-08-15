"""Bing Travel (Fareportal) 数据源适配器。

原理：
  - Bing Travel 搜索结果 URL 携带完整搜索参数（src/des/ddate/rdate），可直接导航。
  - 结果以卡片列表渲染（[data-tag=flightCard]），解析出 价格/时长/经停 等摘要。
  - 对 Top 候选执行“详情充实”（点击进入航班选择视图，提取航段/航班号/航司/转机）。

注意事项：
  - 价格单位 USD，由任务层统一换算 CNY。
  - 卡片价格为“最低往返价格”，最终可订价格以详情/预订页为准。
"""
from __future__ import annotations

import logging
import re
import time
from typing import List, Optional

from ..models import Itinerary, Leg, Segment
from . import FlightSearcher

log = logging.getLogger("flights_zqn.bing")

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

CARD_SEL = "[data-tag=flightCard]"
DONE_MARKER = "航班搜索完成"
NOT_FOUND_MARKERS = ["未找到航班", "找不到", "没有找到"]


def _to_min(hours_str, mins_str) -> int:
    try:
        return int(hours_str) * 60 + int(mins_str or 0)
    except (ValueError, TypeError):
        return 0


def _parse_price(text: str) -> Optional[float]:
    # 国内 cn.bing 直接显示 ¥（人民币），国际版显示 $（USD），两者都支持
    m = re.search(r"¥\s?([\d,]+(?:\.\d+)?)", text) or re.search(r"\$\s?([\d,]+(?:\.\d+)?)", text)
    if m:
        try:
            return float(m.group(1).replace(",", ""))
        except ValueError:
            return None
    return None


class BingSearcher(FlightSearcher):
    name = "bing"
    # 国内 cn.bing 直接以 CNY 计价；国际 www.bing 为 USD（由任务层统一换算）
    currency = None  # 未知，由解析时判定
    needs_browser = True

    def __init__(self, config: dict):
        self.config = config or {}
        self.base = self.config.get("base", "https://www.bing.com/travel/flights")
        self._pw = None
        self._browser = None
        self._ctx = None
        self._page = None

    # ---------------- 浏览器生命周期 ----------------
    def warmup(self) -> None:
        if self._page is not None:
            return
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(
            channel="chrome",
            headless=False,  # Bing 风控会拒绝 headless 无痕访问，必须用 headful + 反检测
            args=["--disable-blink-features=AutomationControlled"],
        )
        self._ctx = self._browser.new_context(
            locale="zh-CN",
            viewport={"width": 1440, "height": 1000},
            # 不用自定义 UA：Bing 风控会对旧版 Chrome UA 返回错误响应，默认 UA 正常
        )
        self._page = self._ctx.new_page()
        # 隐藏自动化指纹
        self._page.add_init_script(
            'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'
        )
        log.info("Bing 浏览器已启动")

    def shutdown(self) -> None:
        for obj in (self._browser,):
            try:
                if obj:
                    obj.close()
            except Exception:  # noqa: BLE001
                pass
        if self._pw:
            try:
                self._pw.stop()
            except Exception:  # noqa: BLE001
                pass
        self._pw = self._browser = self._ctx = self._page = None

    # ---------------- 搜索 ----------------
    def search_roundtrip(self, origin: str, dest: str, depart: str, return_: str,
                         adults: int = 1) -> List[Itinerary]:
        self.warmup()
        page = self._page
        # 用配置的 base 域名（国内网络下 www.bing.com 会 302 到 cn.bing.com）
        base = (self.base or "https://www.bing.com/travel/flights").rstrip("/")
        search_host = base.replace("/travel/flights", "/travel/flight-search")
        url = (
            f"{search_host}"
            f"?src={origin}&des={dest}&ddate={depart}&rdate={return_}"
            f"&cls=0&adult={adults}&child=0&infant=0"
        )
        try:
            # 用 domcontentloaded 而非 load：Bing 的 SPA 在 load 阶段会返回风控错误响应
            page.goto(url, timeout=60000, wait_until="domcontentloaded")
        except Exception as exc:  # noqa: BLE001
            log.warning("Bing 页面加载失败 %s->%s %s~%s: %s", origin, dest, depart, return_, exc)
            return []
        self._wait_results(page)
        cards = page.query_selector_all(CARD_SEL)
        out: List[Itinerary] = []
        seen_price = set()
        for card in cards[:30]:
            try:
                text = (card.inner_text() or "").replace("\n", " ")
            except Exception:  # noqa: BLE001
                continue
            price = _parse_price(text)
            if price is None or price <= 0:
                continue
            it = self._itinerary_from_summary(origin, dest, depart, return_, text, price, card)
            # 去重：同一 (价格, 大致时长) 只保留一个
            k = (round(price), it.outbound.total_min // 60)
            if k in seen_price:
                continue
            seen_price.add(k)
            out.append(it)
        return out

    def _wait_results(self, page, max_wait: int = 60) -> str:
        for _ in range(max_wait // 2):
            time.sleep(2)
            try:
                body = page.inner_text("body")
            except Exception:  # noqa: BLE001
                continue
            if DONE_MARKER in body:
                return "done"
            if any(m in body for m in NOT_FOUND_MARKERS):
                return "not_found"
        return "timeout"

    def _itinerary_from_summary(self, origin, dest, depart, return_, text, price, card) -> Itinerary:
        """从摘要卡片构造 Itinerary（航段细节留空，由 enrich 填充）。"""
        m_dur = re.search(r"(\d+)\s*小时\s*(\d+)?\s*分", text)
        dur_min = _to_min(m_dur.group(1), m_dur.group(2)) if m_dur else 0
        m_stops = re.search(r"经停\s*(\d+)\s*站", text)
        stops = int(m_stops.group(1)) if m_stops else 0
        if "直达" in text:
            stops = 0
        # 时间 "11:35 AM - 12:20 PM+1 天"
        m_t = re.search(r"(\d{1,2}:\d{2}\s*[AP]M)\s*-\s*(\d{1,2}:\d{2}\s*[AP]M)", text)
        dep_t = m_t.group(1) if m_t else ""
        arr_t = m_t.group(2) if m_t else ""

        seg = Segment(
            airline="", flight_no="", dep_airport=origin, arr_airport=dest,
            dep_time=dep_t, arr_time=arr_t, dep_date=depart, arr_date=return_,
            duration_min=0,
        )
        # Bing 摘要卡片给的是「往返合计」的时长与经停数，不是单程；
        # 不能把 stops 同时写进 outbound 和 inbound（filter 会相加导致双重计数）。
        # 这里将总经停数记在 outbound，inbound 置 0（详情 enrich 后再修正）。
        outbound = Leg(segments=[seg], total_min=dur_min, stops=stops)
        inbound = Leg(segments=[], total_min=0, stops=0)
        # 判定币种：¥=CNY（cn.bing），$=USD（www.bing）
        currency = "CNY" if "¥" in text else "USD"
        it = Itinerary(
            origin_airport=origin, dest_airport=dest,
            depart_date=depart, return_date=return_, nights=0,
            outbound=outbound, inbound=inbound,
            price_cny=price, price_orig=price, currency_orig=currency,
            booking_channel="Bing Travel (Fareportal)",
            source="bing",
        )
        it._card = card  # 保留 DOM 引用供 enrich 使用（不序列化）
        return it

    # ---------------- 详情充实 ----------------
    def enrich(self, it: Itinerary) -> bool:
        """进入详情流程提取航段/航班号/航司/转机。返回是否成功。"""
        card = getattr(it, "_card", None)
        if card is None:
            return False
        page = self._page
        try:
            # 展开卡片并点击 选择航班
            card.scroll_into_view_if_needed()
            card.click()
            time.sleep(2)
            btn = None
            for b in page.query_selector_all("button"):
                if "选择航班" in (b.inner_text() or ""):
                    btn = b
                    break
            if btn is None:
                return False
            btn.click()
            time.sleep(4)
            # 此时进入航班选择视图（可能先显示去程或返程）
            out_ok = self._extract_leg_options(page, it.outbound, it)
            # 返回航段选择
            time.sleep(2)
            in_ok = self._extract_leg_options(page, it.inbound, it)
            it.price_verified = out_ok or in_ok
            return out_ok or in_ok
        except Exception as exc:  # noqa: BLE001
            log.warning("Bing enrich 失败: %s", exc)
            return False

    def _extract_leg_options(self, page, leg: Leg, it: Itinerary) -> bool:
        """在航班选择视图中提取当前腿的最优航班信息。"""
        try:
            # 找当前视图的航班选项卡片
            opt_cards = page.query_selector_all("[data-tag=flightCard]")
            if not opt_cards:
                # 尝试其他容器
                opt_cards = page.query_selector_all(".fltbking_list [class*=card], .fltbkig_container [class*=card]")
            if not opt_cards:
                return False
            text = (opt_cards[0].inner_text() or "").replace("\n", " ")
            # 航班号
            fns = re.findall(r"\b([A-Z]{2}\s?\d{3,4})\b", text)
            # 航司名（首段文本）
            m_price = re.search(r"\+\s?\$([\d,]+)", text)
            # 时间
            m_t = re.findall(r"(\d{1,2}:\d{2}\s*[AP]M)", text)
            # 经停
            m_stops = re.search(r"经停\s*(\d+)\s*站", text)
            m_dur = re.search(r"(\d+)\s*小时\s*(\d+)?\s*分", text)
            if m_dur:
                leg.total_min = _to_min(m_dur.group(1), m_dur.group(2))
            if m_stops:
                leg.stops = int(m_stops.group(1))
            if fns:
                for fn in fns[:6]:
                    seg = Segment(
                        airline=fn.split()[0], flight_no=fn.replace(" ", ""),
                        dep_airport="", arr_airport="", dep_time="", arr_time="",
                        dep_date="", arr_date="", duration_min=0,
                    )
                    leg.segments.append(seg)
            return True
        except Exception as exc:  # noqa: BLE001
            log.warning("Bing leg 提取失败: %s", exc)
            return False
