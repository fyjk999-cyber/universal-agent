# PHASE 4 — Hotel + BundleCandidate + 真实源增强 验收报告

> 日期：2026-08-14 · 环境：Python 3.12 · pytest 9.1.1

---

## PHASE COMPLETED

### A. PHASE 4 — Hotel + Travel Bundle（§63/§27/§28）

**Implemented**
- `core/contracts/raw.py` — `RawHotel` 契约（name/geo/brand/room/price/rating）
- `core/contracts/bundle.py` — `BundleCandidate`（§27：components/cost/score，未来可扩 Flight+Hotel+Rail+Transfer）
- `domains/hotel/knowledge.py` — 酒店 Entity Resolution key（name+geo+brand+address，§21）+ Room 归一化（grade/bed/board，§63）
- `domains/hotel/normalize.py` — RawHotel → Candidate/Offer/Quote/Evidence
- `domains/hotel/scoring.py` — 确定性评分（价格/评分/房型）
- `core/bundling/optimizer.py` — **Bundle Optimizer（§28 TOTAL TRIP UTILITY）**：
  - 成本分 + 质量分加权 → utility 排序
  - **`valid_pair` 约束支持**：约束下独立贪心（分别最低）不可达时按总效用选优，并记录证据 note
- `coordinator/scanner/hotel.py` — Hotel 扫描协调器（事件驱动、domain 隔离 RULE 3、源健康降级）
- `domains/travel/bundle.py` — Travel 复合层：flight+hotel 组合（§26）

**Tests（+20）**
| 测试 | 数量 |
|---|---|
| unit/test_hotel.py | 9（entity key/room 归一化/normalize/评分）|
| unit/test_bundle.py | 5（含 **§28 约束非贪心胜出**、note 证据）|
| integration/test_travel_bundle.py | 6（hotel 管线/降级/bundle 组合/去重/约束）|

**端到端实测（fixture）**
```text
3 航班 × 3 酒店 → 9 个 bundle
最优: SHA ¥3,980 + Heritage ¥5,950 = 总 ¥9,930 (score 90.6)
note: "总成本(10210) 优于此前最优，但 flight=...PVG... 非最便宜机票 — 按总效用选优"
```

### B. 真实源增强（第二条线）

**Implemented**
- `adapters/fx/service.py` — **实时汇率服务**（open.er-api.com 免费无 key）：
  缓存优先（TTL 6h）+ 联网刷新 + 离线兜底表；`convert()` 供外币源换算
- `adapters/skyscanner/adapter.py::fetch_many` — **多 query 并发**（`asyncio.Semaphore` 限流，尊重 robots；§48 单 query 失败隔离）
- `adapters/official/registry.py` — **Tier3 官方源验证骨架**：
  - `OfficialSourceRegistry`（注册/健康/失败降级）
  - `NoOpOfficialVerifier`（骨架占位，不伪造结果）+ `StubOfficialVerifier`（测试用）
  - 合规（§56）：不登录/不购买/不绕过验证码

**Tests（+7）**：unit/test_fx_concurrency_official.py — 缓存命中/离线兜底/CNY 直通/并发失败隔离/官方源 T3 验证/失败降级

**端到端实测**
```text
实时汇率: GBP→CNY(1234) = ¥11,242 (rate 0.109773, open.er-api 实测)
并发抓取: fetch_many 3 query 限流并发，单源失败隔离（mock 验证）
```

**Known limitations**
- 真实并发抓取浏览器开销大（3 并发曾超 180s）——真实场景建议 max_concurrency=1~2
- Tier3 官方源仅骨架（NoOp 不伪造）；具体航司适配器按需接入
- Bundle 约束默认无（成本线性可分时贪心=最优）；约束场景由上层传入
- 汇率缓存 TTL 6h；无网络时用兜底表（可能过时）

**Security / 合规**
- SHADOW MODE 保持；无购买/登录/凭据
- 官方源骨架不绕过验证码；Skyscanner 尊重 robots（Crawl-Delay）
- Bundle 评分全确定性，无 LLM（RULE 7）

**Host coupling audit**：CLEAN ✓（新增全在 domains/core/coordinator/adapters）

**Migration compatibility**：Jarvis Host Swap Test 通过（186 全绿，Core 零修改）

**Next phase**
- **PHASE 5 — CareerPilot Migration Test**（Job Domain 接入，证明 Universal Core 直接处理 Job）
- 或：Skyscanner 真实并发调优 + Tier3 航司适配器（NZ/Air NZ 官网）
