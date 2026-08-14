# PHASE 3b — 真实数据源接入（Skyscanner Tier2）验收报告

> 日期：2026-08-14 · 环境：Python 3.12 · scrapling 0.4.14（本机 Chrome）· pytest 9.1.1

---

## PHASE COMPLETED

**Implemented（§62 多源 + §53 健康降级 + §56 合规）**
- `adapters/skyscanner/adapter.py` — 真实 Skyscanner 源：
  - scrapling `StealthyFetcher` 浏览器渲染（SPA），`real_chrome` 用本机 Chrome
    （避免下载 playwright chromium——国内 CDN 该 build 不可用）
  - 尊重 robots.txt（`User-agent: *` 无 disallow，`Crawl-Delay: 2` 已内置延迟）
  - 整页 regex 提取 `Price_mainPriceContainer` 价格 + 时长配对（实测比 CSS 卡片容器完整）
  - 多货币支持：`£/$/US$/¥/€` 检测 + `to_cny` 换算（支持 open.er-api 格式与兜底表）
  - 价格去重（§71）
- `adapters/skyscanner/manifest.py` — SkillManifest（search/price_verify=true，
  execute_order=false）+ MarketplaceManifest（trust 0.8）
- `coordinator/scanner/shadow.py`：
  - **`asyncio.to_thread` 包装同步 fetcher**（修复 Playwright Sync API 在 asyncio
    loop 内被拒绝的问题）
  - **§53 健康降级**：源异常 → 自动标记 DEGRADED → 后续跳过，不中断整体
- `apps/shadow_scan.py --live`：真实源 CLI 入口

**Tests — 159 passed（新增 16）**
| 测试 | 内容 |
|---|---|
| unit/test_skyscanner_adapter.py (12) | 价格/时长/货币解析、URL、bot-wall 降级、卡片解析、to_cny |
| integration/test_live_source.py (4) | manifest 声明、源失败→DEGRADED、DEGRADED 被选源排除 |

**真实抓取实测（2026-08-14，Skyscanner PVG→ZQN）**
```text
HTTP 200；解析出多档价格：¥7,716 / ¥11,242 / ¥11,260 / ¥18,211（GBP→CNY 换算）
混合源管线：ctrip(replay) + skyscanner(真实) → 8 条 raw → Top5 生成
skyscanner health: HEALTHY
```

**Known limitations**
- 真实抓取较慢（每次 ~20-50s，浏览器渲染+爬虫延迟），符合 Tier2 定位：
  仅验证用，不参与每轮全量（§25 tiering）
- Skyscanner 国际版默认显示外币（GBP/USD），经汇率换算为 CNY；汇率用缓存/
  兜底表，未接实时汇率服务（可复用旧项目 `scanner/fx.py`）
- 解析基于当前页面结构 regex，站点改版需重新适配（容错：解析失败降级为空，
  不崩溃）
- 未实现 Tier3 官方源（航司官网验证）——需逐一接航司，Phase 4+ 候选

**Security / 合规（§56）**
- 未绕过验证码：检测到 bot-wall → `SourceUnavailable` → 降级（实测验证）
- 未逆向私有 API；仅解析公开搜索结果页面
- 尊重 robots.txt（Crawl-Delay）
- 仍 SHADOW MODE：无购买、无登录、无凭据

**Host coupling audit**：CLEAN ✓（真实源在 adapters 层，Core 无改动）

**Migration compatibility**：Jarvis Host Swap Test 继续通过（159 全绿）

**Next phase**
- **PHASE 4 — Hotel + BundleCandidate**（Flight+Hotel 联合决策）
- 或：Tier3 官方源验证 + 汇率实时接入 + Skyscanner 多 query 并发提速
