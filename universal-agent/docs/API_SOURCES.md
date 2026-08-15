# API 数据源接入指南（CH4 多源 · 真实数据）

> 更新：2026-08-15（v2：新增 Aviationstack 实时状态 + 借自本地"机票 OS"的中文城市解析/航司名录）

## 当前可用的真实源

| Source | 类型 | 状态 | 启用条件 |
|---|---|---|---|
| Skyscanner（浏览器抓取） | Flight Live | ✅ 已启用（`--live`） | 本机 Chrome + scrapling（既有） |
| **Kiwi Tequila**（推荐） | Flight 价格 API | ✅ 适配器已实现（`adapters/kiwi/`） | 注册免费 key → `UA_KIWI_KEY` |
| **12306 公开接口**（国内火车） | Railway 真实数据 | ✅ **已接入且实测出数据**（`adapters/railway/`，无 key） | 无需配置，直接可用 |
| **Aviationstack**（实时状态） | Flight 运营数据 | ✅ 适配器已实现（`adapters/aviationstack/`） | 注册免费 key → `UA_AVIATIONSTACK_KEY`（本机已有，可复用） |
| Ctrip HTTP（可配置端点） | Flight | ✅ 适配器已实现（`adapters/ctrip/`） | 提供 JSON 端点 → `UA_CTRIP_ENDPOINT` |
| Booking HTTP（可配置端点） | Hotel | ✅ 适配器已实现（`adapters/booking/`） | 提供 JSON 端点 → `UA_BOOKING_ENDPOINT` |

## ✅ 国内真实数据：12306（无 key，已实测）

12306 公开匿名接口（`kyfw.12306.cn`）无需注册，直接可查国内火车**余票 + 时刻**：

```bash
# 完整流程（Scan→Normalize→Score→Rank→Opportunity→Notify）
python -m universal_agent.apps.agent_cli --domain railway
# → raw=20 candidates=4；#1 G7357 08:00→09:36 一等座 余票=01 score=91
# → [机会] G7357 上海→杭州东 2026-08-20 08:00 一等座 余票=01
# → [通知] 已投递

# 程序化使用
from universal_agent.adapters.railway import Railway12306Skill
skill = Railway12306Skill()
items = skill.search({"from_city": "上海", "to_city": "杭州东", "date": "2026-08-20"})

# 完整协调器（Watch 用）
from universal_agent.coordinator.scanner import RailwayScanCoordinator
```

- 实现：`adapters/railway/`（会话初始化 → 车站表 → queryG 余票/时刻；精确车站匹配；
  票价端点 best-effort，限流时 fail-closed UNKNOWN）
- 礼貌：每次查询间隔 1s；不做登录态/验证码绕过（SPAC §33）
- 局限：票价端点（`leftTicketPrice`）对匿名请求限流严重，当前返回余票 + 时刻；
  **接入登录态后显示实时票价**：
  ```bash
  # 从浏览器 12306 登录态复制 Cookie（含 JSESSIONID）→ 看板票价列显示真实票价
  export UA_12306_COOKIE="JSESSIONID=xxx; ..."
  ```

## 国内其它源的可抓性评估（2026-08-15 实测）

| 源 | 实测 | 结论 |
|---|---|---|
| **航旅纵横（umetrip）** | 首页可达，但航班动态/行程需登录；无公开价格 API | 不合规抓取（登录态），不接入（SPAC §33） |
| **去哪儿（qunar）** | `search.qunar.com` SSL 阻断；`flight.qunar.com/touch/api` 返回 HTML（反爬墙） | 反爬墙，不绕过（SPAC §33 非目标） |
| **携程（ctrip）** | `flights.ctrip.com` 返回 432（风控） | 反爬墙，不绕过 |
| **同程（ly.com）** | 首页 200，无公开价格 API | — |

> 结论：国内**航班价格**没有公开免费 API（携程/去哪儿/飞常准/航旅纵横均为商业或登录制）；
> 合规可接入的真实国内数据 = **12306（火车，无 key，已接入）** + 天巡中国站（Skyscanner 模式）。
> 如需国内航班价格，合法路径是商业 API（如飞常准企业版）或用户自有账号数据。

## 推荐：Kiwi Tequila（航班价格，覆盖 SHA/PVG/HGH → ZQN）

2026-08-15 实测：`tequila-api.kiwi.com` 从本机可达，认证语义正确
（无 key → 403 "apikey header is required"；假 key → 401 Unauthorized）。
管线已通，只差一个真实 key。

### 获取 key（2 分钟）

1. 打开 https://partners.kiwi.com/ → Sign Up（免费注册）
2. 登录后进入 **API access** → 创建应用 → 拿到 **API Key**
3. ⚠️ 注意（2026-08 情报）：部分来源报告 Tequila 新注册可能要求付费套餐
   （[php.cn 403 分析](https://www.php.cn/faq/2865859.html)）；
   若注册后无法免费获取 key，可改用下方 Amadeus 替代或使用你自己找的端点。

### 启用

```bash
export UA_KIWI_KEY=你的key
# 验证
python -m universal_agent.apps.agent_cli --health --data-dir /tmp/ua-svc
# 跑真实多源扫描（replay fixture + skyscanner + kiwi）
python -m universal_agent.apps.scheduler --tasks-dir tasks --data-dir data \
    --sources ctrip,fliggy --live
```

### 可选配置

| 环境变量 | 默认 | 说明 |
|---|---|---|
| `UA_KIWI_KEY` | — | Tequila apikey（必填） |
| `UA_KIWI_ENDPOINT` | `https://tequila-api.kiwi.com/v2` | 端点覆盖 |
| `UA_KIWI_CURRENCY`（代码内） | CNY | 币种 |

## 不推荐：Amadeus Self-Service（注意）

Amadeus 自助开发者门户**正在关停**（[phocuswire 报道](https://www.phocuswire.com/amadeus-shut-down-self-service-apis-portal-developers)），
且本机实测 `api.amadeus.com` / `test.api.amadeus.com` DNS 不可达。
新项目不建议依赖。

## ✅ Aviationstack 实时航班状态（运营数据，非票价）

2026-08-15 实测（本机 key 有效）：`api.aviationstack.com` 可达，
按航班号 + 日期返回实时状态 / 航站楼 / 登机口 / 延误 / 预计与实际起降时间。

```bash
export UA_AVIATIONSTACK_KEY="你的 key"   # 本机旧项目 .env 已有可用 key
python -m universal_agent.apps.dashboard --port 8632
# 看板 Flight 面板"实时状态"列即显示（CA123 → PEK T3）
```

- 实现：`adapters/aviationstack/`（SkillProtocol：search/detail/verify/availability/
  prepare_action/health_check；无 execute）
- 边界（诚实标注，§33 不混淆）：**运营状态不是可售票价/舱位**；
  免费档 `flight_iata` 为模糊匹配 → 代码内**精确匹配优先**（CA123 不取 SC123）；
  查不到/无 key → 显式 `AUTH_REQUIRED` / `found=False`（RULE-009）
- 局限：免费档未来日期排班可能不在权限内（如实显示"无记录"，不伪造）

## ✅ 借自本地"机票 OS"的知识资产（2026-08-15 移植）

来源：`/Users/huhongjie/Documents/Codex/2026-07-23/referenced-chatgpt-conversation-this-is-untrusted-2/`
（旅程智选 Travel Reward Optimizer，2026-07 本地项目，用户授权借鉴）。

| 资产 | 落位 | 说明 |
|---|---|---|
| 中文城市→机场 IATA 别名表（29 机场） | `domains/flight/airports.py` | "上海"→PVG、"东京"→NRT；Kiwi/看板直接支持中文输入 |
| 中国航司名录（46 家，民航局） | `domains/flight/airports.py` | 航司中文名 + 官方购票 URL；看板"官网核价"链接 |
| Aviationstack 接入经验 + 复用 key | `adapters/aviationstack/` | 见上节 |
| Chrome 会话桥 MV3 扩展（白名单默认拒绝） | `adapters/browser/chrome_bridge/`（由 `scripts/gen_chrome_bridge.py` 从航司名录生成） | 人机协同打开官方页面；不碰 Cookie/密码/支付（FR-060-062 蓝图） |

不借鉴：原项目"演示票价 fallback"（模拟数据冒充真实，违反 RULE-009/SPAC §56）。

## 自行接入任意 JSON 端点（Ctrip/Booking 模式）

若你有任何返回 JSON 的航班/酒店数据端点（自建、第三方、或商业 API），
按 `adapters/ctrip/` 与 `adapters/booking/` 的 JSON 契约实现即可：

- 航班契约：`{listing_id, origin, destination, depart_date, return_date,
  price_cny, outbound[], inbound[]}`（缺关键字段自动 fail-closed 跳过）
- 酒店契约：`{hotel_id, name, city, check_in, check_out, price_per_night_cny, ...}`

```bash
export UA_CTRIP_ENDPOINT=https://你的端点/flights
export UA_BOOKING_ENDPOINT=https://你的端点/hotels
```

## 验证链路

```bash
cd universal-agent
../.venv/bin/python -m pytest tests/integration/test_kiwi_source.py -q   # Kiwi 5 项
../.venv/bin/python -m pytest tests/integration/test_aviationstack_source.py -q  # 状态源 7 项（有 key 时含真实端点）
../.venv/bin/python -m pytest tests/unit/test_flight_airports.py -q      # 中文解析+航司名录 11 项
../.venv/bin/python -m pytest tests/unit/test_browser_bridge.py -q       # 会话桥白名单/审批 13 项
../.venv/bin/python -m pytest tests/integration/test_dashboard_flight.py -q  # 看板端点 6 项
../.venv/bin/python -m pytest tests/integration/test_ch4_multi_source.py -q  # 多源 5 项
../.venv/bin/python -m universal_agent.apps.agent_cli --health
```

## 边界（SPAC §33 Non-Goals）

- 不绕过平台验证码/风控；只用公开 API/公开搜索端点 + 合法 key
- 不登录态自动购买；SKill 不执行（FR-056）
- 源不可达时必须显式 `DEGRADED/UNAVAILABLE`（FR-055），不静默脑补（RULE-009）
