# PHASE 3 — Multi-Source Flight Watch（增量）验收报告

> 日期：2026-08-14 · 环境：Python 3.12.13 · pytest 9.1.1
> 前置：PHASE 2 验收发现缺陷 → 按用户决策先修复 → 回归 → 继续 PHASE 3

---

## 缺陷修复（验收发现，已修复）

**缺陷**：host adapter 绕过状态机 —— `harness/adapter.py` 与 `jarvis/adapter.py`
原以字符串直接赋 `task.state = "PAUSED"`（`# type: ignore`），未走
`state_machine.transition()` 校验，触发 Pydantic 序列化警告（实测复现 2 处）。

**修复**：
- 两个 adapter 的 pause/resume/cancel 改用 `WatchState` 枚举 + `transition()` 校验
- resume 语义修正：仅 PAUSED→WATCHING，其它状态 no-op（不抛异常）
- 新增回归测试 `tests/unit/test_adapter_state_machine.py`（6 项）：枚举赋值、
  无警告序列化（`warnings.simplefilter("error")` 下通过）、非法转移抛
  TransitionError、非 PAUSED resume 为 no-op
- 同步修正 host_swap 测试使用合法转移序列（DRAFT→ACTIVE→PAUSED→WATCHING）

## PHASE 3 新增能力

**Implemented**
- `core/verification/verifier.py` — Verification 分级（§25/§31/§62）：
  - Tier1/2/3/4 置信度增量；cross-source agreement 提升置信度
  - 价格离散容差检查（spread 超限 → failed）
  - 细粒度 Confidence（price/availability/schedule/baggage/final）+ Evidence 列表
  - 确定性验证（verified_by = deterministic_T*，无 LLM）
- Observation 历史键修复：`ObservationStore.record_price` 新增 `entity_key` 参数，
  按稳定实体键累积跨轮价格历史（此前按每次扫描新生成的 offer_id 记录，
  无法跨轮统计）
- `ObservationStore.quotes_history(entity_key)` — 从事实历史重建 Quote 列表
- Shadow Scan 协调器升级：
  - VERIFICATION_COMPLETED 事件接入（T2 + cross-source 提升）
  - Opportunity 改用完整实体历史（§32 多轮统计）
  - verification 置信度注入 Opportunity 评分
  - Quote 新增 `source` 字段（来源追溯）
- `ScanOutcome.verification` 字段 + CLI 展示验证/机会信息

**Tests — 143 passed（新增 9）**
| 区域 | 新增 |
|---|---|
| unit/test_verification.py | 5（T2/cross-source 提升/spread 失败/tier 递增/细粒度字段）|
| integration/test_phase3.py | 4（验证事件/多轮历史累积/历史低/置信度注入）|
| unit/test_adapter_state_machine.py | 6（回归，参数化双 adapter）|

**Demo（CLI 实测输出）**
```text
Top5: SHA ¥3980 / PVG ¥4260 / HGH ¥4380 / PVG ¥4520 / HGH ¥5080
[验证] deterministic_T2 passed=True confidence=0.785 evidence=1条
[机会] score=75.4 hist_low=True drop=¥0 (0.0%)
```

**Known limitations**
- Verification 仍基于同轮报价（Tier2/3 的 booking_detail/官方验证需真实源，
  Phase 4/接真实数据时实现）
- Opportunity 历史当前来自 fixture 回放（同价重复扫描），真实价格波动统计
  需真实源多轮采集
- Bundle（Flight+Hotel）未实现（Phase 4）

**Security status**
- 仍 SHADOW MODE，无执行事件；验证全确定性，无 LLM 判断
- Action Gateway L2+ 仍硬阻塞

**Host coupling audit**
- Core/domains/coordinator/adapters 对 hosts/harness 真实 import：**CLEAN ✓**

**Migration compatibility**
- Jarvis Host Swap Test 通过（修复后仍 0 Core 修改）；adapter 改动仅涉及
  状态机用法，未改 HostProtocol 契约

**Next phase**
- **PHASE 4 — Hotel + BundleCandidate**（Flight+Hotel 联合决策）
- 或接真实数据源（scrapling/playwright 合法公开源）实现 Tier2/3 真实验证
