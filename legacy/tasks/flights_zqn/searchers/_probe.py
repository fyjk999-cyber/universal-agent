"""数据源探测脚本：用 Scrapling 加载各机票站点，验证可访问性并抓取结果。

用法: .venv/bin/python tasks/flights_zqn/searchers/_probe.py <bing|qunar|ctrip>
"""
import sys, time, json

sys.path.insert(0, ".")

def probe_bing():
    from scrapling.fetchers import DynamicFetcher
    url = "https://www.bing.com/travel/flights?from=HGH&to=ZQN&depart=2026-08-30&return=2026-09-06"
    page = DynamicFetcher.fetch(url, headless=True, network_idle=True, timeout=45000)
    html = page.html_content if hasattr(page, "html_content") else str(page)
    print("HTML len:", len(html))
    open("/tmp/probe/bing_result.html", "w").write(html)
    # 看是否出现机票结果关键字
    for kw in ["Queenstown", "ZQN", "flight", "result", "CAD", "USD"]:
        print(kw, kw.lower() in html.lower())

def probe_qunar():
    from scrapling.fetchers import DynamicFetcher
    url = "https://flight.qunar.com/international/?from=HGH&to=ZQN&depdate=2026-08-30&retdate=2026-09-06"
    page = DynamicFetcher.fetch(url, headless=True, network_idle=True, timeout=45000)
    html = page.html_content if hasattr(page, "html_content") else str(page)
    print("HTML len:", len(html))
    open("/tmp/probe/qunar_result.html", "w").write(html)
    for kw in ["皇后镇", "ZQN", "价格", "机票", "去程"]:
        print(kw, kw in html)

def probe_ctrip():
    from scrapling.fetchers import StealthyFetcher
    url = "https://flights.ctrip.com/international/search/oneway-hgh-zqn?depdate=2026-08-30"
    page = StealthyFetcher.fetch(url, headless=True, network_idle=True, timeout=60000, solve_cloudflare=True)
    html = page.html_content if hasattr(page, "html_content") else str(page)
    print("HTML len:", len(html))
    open("/tmp/probe/ctrip_result.html", "w").write(html)
    for kw in ["皇后镇", "ZQN", "价格", "最低价"]:
        print(kw, kw in html)

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "bing"
    {"bing": probe_bing, "qunar": probe_qunar, "ctrip": probe_ctrip}[target]()
