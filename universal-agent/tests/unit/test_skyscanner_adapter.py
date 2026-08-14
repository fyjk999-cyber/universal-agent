"""Skyscanner adapter tests — parsing + bot-wall handling (§53, §56).

浏览器渲染不在此测试（离线）。解析逻辑用构造的 HTML 验证；风控/超时
路径验证 SourceUnavailable 抛出与健康标记。
"""
from __future__ import annotations

import pytest

from universal_agent.adapters.skyscanner import (
    SkyscannerAdapter,
    SkyscannerConfig,
    SourceUnavailable,
)
from universal_agent.adapters.skyscanner.adapter import (
    _detect_currency,
    _parse_duration,
    _parse_price,
    _search_url,
    to_cny,
)
from universal_agent.coordinator.query_planner import FlightQuery


def _q() -> FlightQuery:
    return FlightQuery(origin="PVG", destination="ZQN",
                       depart_date="2026-08-31", return_date="2026-09-07", nights=7)


class TestParsers:
    def test_parse_price_yuan(self):
        assert _parse_price("¥4,380") == 4380.0
        assert _parse_price("CNY 4,380") == 4380.0
        assert _parse_price("¥ 3980") == 3980.0

    def test_parse_price_none(self):
        assert _parse_price("no price here") is None

    def test_parse_price_foreign_currency(self):
        assert _parse_price("£1,234") == 1234.0
        assert _parse_price("US$2,862") == 2862.0

    def test_detect_currency(self):
        assert _detect_currency("£1,234") == "GBP"
        assert _detect_currency("¥4,380") == "CNY"
        assert _detect_currency("no price") == "CNY"

    def test_to_cny_fallback(self):
        assert to_cny(1234, "GBP") > 10000  # £1,234 ≈ ¥11,2xx
        assert to_cny(4380, "CNY") == 4380

    def test_to_cny_rates_format(self):
        # open.er-api 格式：1 CNY 兑 0.1097 GBP → 除法
        assert to_cny(1234, "GBP", {"GBP": 0.1097}) == 11248.86

    def test_parse_duration(self):
        assert _parse_duration("18h 25m") == 1105
        assert _parse_duration("2h") == 120
        assert _parse_duration("45m") == 45

    def test_search_url_shape(self):
        url = _search_url(_q())
        assert "PVG/ZQN/260831/260907" in url
        assert "rtn=1" in url


class TestAdapterParse:
    def test_bot_wall_raises_source_unavailable(self):
        """§56: 风控时降级（SourceUnavailable），绝不绕过验证码。"""
        adapter = SkyscannerAdapter(config=SkyscannerConfig(request_delay_sec=0))
        class FakePage:
            status = 200
            body = "<html>Please verify that you are a real user captcha</html>"
        with pytest.raises(SourceUnavailable):
            adapter._parse_results(FakePage(), _q())

    def test_empty_page_returns_empty(self):
        adapter = SkyscannerAdapter(config=SkyscannerConfig(request_delay_sec=0))
        class FakePage:
            status = 200
            body = "<html><body>nothing here</body></html>"
        assert adapter._parse_results(FakePage(), _q()) == []

    def test_parses_cards_to_raw_listings(self):
        """用真实 Skyscanner 结构（Price_mainPriceContainer）验证解析。"""
        adapter = SkyscannerAdapter(config=SkyscannerConfig(request_delay_sec=0))
        html = """
        <html><body>
          <div class="Price_mainPriceContainer__NzBmO">
            <span class="BpkText_bpk-text__NzllM" data-backpack-ds-component="Text">¥4,380</span>
          </div>
          <span class="visually-hidden">18 hours 25 minutes average</span>
          <div class="Price_mainPriceContainer__NzBmO">
            <span class="BpkText_bpk-text__NzllM" data-backpack-ds-component="Text">¥5,080</span>
          </div>
          <span class="visually-hidden">22 hours 10 minutes average</span>
        </body></html>
        """
        from scrapling.parser import Selector
        page = Selector(html)
        listings = adapter._parse_results(page, _q())
        assert len(listings) == 2
        assert listings[0].price_cny == 4380.0
        assert listings[1].price_cny == 5080.0
        assert listings[0].origin_airport == "PVG"
        assert listings[0].marketplace_id == "skyscanner"
        assert listings[0].nights == 7

    def test_parse_skips_card_without_price(self):
        adapter = SkyscannerAdapter(config=SkyscannerConfig(request_delay_sec=0))
        html = """
        <div data-testid="flights-result-card"><span>no price</span></div>
        """
        from scrapling.parser import Selector
        assert adapter._parse_results(Selector(html), _q()) == []
