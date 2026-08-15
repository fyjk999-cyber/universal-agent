# API 数据源接入指南（CH4 多源 · 真实数据）

> 更新：2026-08-15 · 目标：让多源管线接上**真实**航班/酒店价格数据（不再只用 replay fixture）。

## 当前可用的真实源

| Source | 类型 | 状态 | 启用条件 |
|---|---|---|---|
| Skyscanner（浏览器抓取） | Flight Live | ✅ 已启用（`--live`） | 本机 Chrome + scrapling（既有） |
| **Kiwi Tequila**（推荐） | Flight 价格 API | ✅ 适配器已实现（`adapters/kiwi/`） | 注册免费 key → `UA_KIWI_KEY` |
| Ctrip HTTP（可配置端点） | Flight | ✅ 适配器已实现（`adapters/ctrip/`） | 提供 JSON 端点 → `UA_CTRIP_ENDPOINT` |
| Booking HTTP（可配置端点） | Hotel | ✅ 适配器已实现（`adapters/booking/`） | 提供 JSON 端点 → `UA_BOOKING_ENDPOINT` |

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
../.venv/bin/python -m pytest tests/integration/test_ch4_multi_source.py -q  # 多源 5 项
../.venv/bin/python -m universal_agent.apps.agent_cli --health
```

## 边界（SPAC §33 Non-Goals）

- 不绕过平台验证码/风控；只用公开 API/公开搜索端点 + 合法 key
- 不登录态自动购买；SKill 不执行（FR-056）
- 源不可达时必须显式 `DEGRADED/UNAVAILABLE`（FR-055），不静默脑补（RULE-009）
