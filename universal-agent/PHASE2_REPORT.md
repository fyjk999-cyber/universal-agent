# PHASE 2 — Flight Shadow Vertical Slice 验收报告

> 日期：2026-08-14 · 环境：Python 3.12.13 · pydantic 2.13.4 · pytest 9.1.1
> 流程：free-dp-pro（DSH 主 agent 整合 + 审核；无专家版委托 —— 环境无 DeepSeek 网页版桥接，按运行时能力规则保持当前能力路径，未假装切换）

---

## PHASE COMPLETED

**Implemented（§61 全流程，SHADOW MODE）**
- `core/contracts/raw.py` — RawListing/RawLeg/RawSegment 契约（§19/§47）
- `domains/flight/` — 领域知识（RULE 3）：entity_key（§21）/ attributes / normalize（§20）
- `domains/flight/scoring.py` — 确定性评分（价格/转机/时长/质量，RULE 7 无 LLM）
- `core/ranking/ranker.py` — Top5 多样性排名（最佳/最低价/最短/每出发城市代表）
- `core/change_detection/detector.py` — 材料变化检测（§71 同价不重复通知）
- `core/opportunity/engine.py` — OpportunityScore（§32 历史低/跌幅/分位/信任/验证）
- `coordinator/query_planner/` — QueryPlanner（§24 搜索什么）
- `coordinator/source_planner/` — SourcePlanner（§24/§25/§53 去哪里搜，健康度+信任排序）
- `coordinator/trigger_engine/` — Trigger 评估（§33）
- `coordinator/scanner/shadow.py` — 事件驱动 Shadow Scan 协调器（§7 全事件链）
- `adapters/replay/` — Replay 源适配器（§47，按 origin+日期精确匹配）
- `memory/observations/` — ObservationStore（§29 事实历史）
- `apps/shadow_scan.py` — 可运行 CLI（Queenstown Top5 推荐）
- `tests/replay/fixtures/{ctrip,fliggy}.json` — 回放 fixture（§47）

**Contracts added**
- RawListing v1（listing_id/source/marketplace_id/task_id/origin/dest/dates/nights/price/outbound/inbound/url/luggage）
- ScanOutcome（trace_id/task_id/candidates/offers/quotes/raw_listings/top5/opportunity/notified/emitted_events）

**Tests — 126 passed（新增 36）**
| 区域 | 数量 | 新增 |
|---|---|---|
| unit | 51 | flight_normalize(8) / flight_scoring(5) / opportunity_trigger(7) / planners(6) |
| integration | 11 | **shadow_scan(4：全事件链/跨源合并/Observation 持久化/Shadow 无执行)** + event_bridge(2) |
| replay | 3+1 | fixture 加载 / origin+日期过滤 / **跨源 entity resolution** |

**Coverage（PHASE 2 关键路径）**
- 全事件链：SCAN_REQUESTED → RAW_LISTING_DISCOVERED → CANDIDATE_CREATED → OFFER_DISCOVERED → QUOTE_OBSERVED → SCORE_UPDATED → MATERIAL_CHANGE_DETECTED → OPPORTUNITY_DETECTED → NOTIFICATION_REQUESTED → NOTIFICATION_SENT → SCAN_COMPLETED —— 覆盖
- 单 trace_id 贯穿（§51）—— 覆盖
- 跨源 Entity Resolution：ctrip+fliggy 同航班（PVG→ZQN 08-30 MU779+NZ621）合并为同一 Candidate —— 覆盖
- Shadow 模式零执行事件（§61/§56）—— 覆盖
- 通知去重：同价不重发（§71）—— 覆盖

**Demo 输出（Queenstown，fixture 回放）**
```text
raw_listings: 5   candidates: 4   quotes: 5   notified: true
Top5: SHA→ZQN ¥3980 / PVG→ZQN ¥4260 / HGH→ZQN ¥4380 / PVG→ZQN ¥4520 / HGH→ZQN ¥5080
```

**Known limitations**
- 数据源为 fixture 回放（Phase 2 按计划不接真实平台；真实 Skill/Adapter 在 Phase 3 接）
- Opportunity 历史仅当前 scan 内 quote（多轮历史统计在 Phase 3 Observation 累积后做）
- Verification 分层（Tier2/3 验证）未实现，验证置信度为固定默认值
- Bundle（Flight+Hotel）未实现（Phase 4）

**Security status**
- SHADOW MODE：无真实支付/购票/凭据；CLI 仅读 fixture
- Action Gateway 仍只开放 L0/L1，L2+ 硬阻塞（未变）

**Host coupling audit**
- Core + domains + coordinator + adapters 对 hosts/harness 的真实 import：**CLEAN ✓**（grep 验证）

**Migration compatibility**
- Jarvis Host Swap Test 继续通过（§46/§73，Core 零修改）
- PHASE 2 全部新增逻辑位于 Core/domains/coordinator/adapters，未触碰 hosts 层

**Next phase**
- **PHASE 3 — Multi-Source Flight Watch**：接真实 Skill（含 scrapling/playwright 适配器）+ Verification 分级 + Evidence 完整性 + Opportunity 历史统计 + Source Health 驱动选源

---

## 与验收核心问题（§72）对照
| 问题 | 状态 |
|---|---|
| 现在有哪些 Active Watch？ | TaskRegistry.active_watches() ✓ |
| 为什么今天提醒？ | TriggerEngine reasons ✓ |
| 同一个航班不同平台多少钱？ | 跨源 Quote/Offer 对比（fixture 演示）✓ |
| 哪个报价已验证？ | Quote.confidence + Evidence ✓（分级验证 Phase 3）|
| 为什么选择这个平台？ | SourcePlanner 信任排序 ✓ |
| 使用了哪个 Skill？ | registry + fetcher 来源标记 ✓ |
| 数据证据是什么？ | Evidence（source/method/snapshot/confidence）✓ |
| Task 失败后能否恢复？ | Checkpoint + Registry JSON 持久化 ✓ |
| 切换 Jarvis 是否改 Core？ | **NO** ✓ |
