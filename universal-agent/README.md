# Universal Persistent Watch & Decision Agent

**Host-Agnostic + Contract-First + Event-Driven + Replaceable**

长期存在的个人监控与决策基础设施，不是单一搜索 Agent。

```text
REMEMBER → WATCH → OBSERVE → NORMALIZE → COMPARE → VERIFY → DECIDE
    → NOTIFY → ACT → VERIFY ACTION → LEARN → REMEMBER
```

支持 Domain：`Flight / Hotel / Railway / Ecommerce / Food / Jobs / Future`
支持任务：`OneShot / Scheduled / Watch / ConditionWatch / Composite / MultiDomain`

## 架构（核心铁律）

```text
DeepSeek Harness (当前 Host)
        ↓
HarnessHostAdapter
        ↓
HostProtocol
        ↓
Universal Agent (本包)
```

- **RULE 1**：Core 不依赖任何 Host（当前是 DeepSeek Harness）。
- **RULE 2**：未来 Jarvis 接入只新增 `JarvisHostAdapter`，禁止重构 Core/Memory/Domain/Skill/Watch/Scheduler/Action Gateway。
- **RULE 6**：一切外部副作用必须经过 Action Gateway。
- **RULE 7**：LLM 不进核心确定性数据链（Filter/Dedup/Scoring/Ranking/Change Detection 程序化）。
- **RULE 8**：Observation → Evidence → Decision 分离，禁止"LLM 认为价格是 X"。
- **RULE 10**：所有重要行为可追踪、可重放、可解释、可恢复。

## 目录速览

```text
universal_agent/
├── core/contracts/        # 冻结的数据契约（Pydantic v2）
├── core/state_machine.py  # WatchTask 显式状态机
├── events/                # EventEnvelope + EventBusProtocol + InProcessEventBus
├── hosts/protocol/        # HostProtocol（Core 唯一允许依赖的 Host 面）
├── hosts/deepseek_harness/# 当前 Host 适配器
├── hosts/jarvis/          # 未来 Host 适配器（mock）
├── coordinator/           # TaskRegistry / Scheduler / WatchManager / Checkpoint
├── memory/                # Core 拥有的 Memory（scope 化）
├── registry/              # Skill/Marketplace Registry + capability 强制
├── actions/gateway/       # Action Gateway（V1 仅 L0/L1）
└── notifications/         # 通知去重（fingerprint + cooldown）
```

## 当前状态

- **PHASE 0 完成**：Contracts / Event Protocol / HostProtocol / 状态机 / Memory / Registry / Gateway / Contract Tests
- **PHASE 1 skeleton 完成**：EventBus / TaskRegistry / BaselineScheduler / WatchManager / Checkpoint / Notification / Harness Adapter / Mock Jarvis Adapter
- **PHASE 2 完成（Flight Shadow Vertical Slice）**：QueryPlanner → SourcePlanner → Replay 源 → Normalize → Candidate/Offer/Quote → 跨源 Entity Resolution → 确定性评分 → Top5 → Change Detection → Opportunity → Trigger → Notify，全事件驱动（SHADOW MODE，不购买）
- **PHASE 3 完成（多源增强）**：Verification 分级（Tier1-4）+ Evidence + Opportunity 历史统计（Observation 按 entity_key 跨轮累积）
- **PHASE 3b 完成（真实数据源）**：Skyscanner 浏览器抓取（scrapling + 本机 Chrome）、多货币换算、Source Health 降级（§53）、`--live` CLI
- **PHASE 4 完成（Hotel + Bundle）**：Hotel 领域（Entity Resolution/Room 归一化/评分）+ BundleCandidate + Bundle Optimizer（§28 TOTAL TRIP UTILITY，约束下非贪心选优）
- **真实源增强完成**：实时汇率服务（open.er-api 缓存+兜底）、多 query 并发抓取（限流+失败隔离）、Tier3 官方源验证骨架
- **PHASE 5 完成（CareerPilot Migration Test）**：Job Domain 接入证明 Universal Core 零修改处理 Job Candidate/Job Watch/Application ActionPlan/Answer Memory
- **PHASE 6 完成（Action Preparation）**：风险控制骨架（Idempotency §38 / Slippage §39 / Approval Inbox §41 / Audit §50）+ L2 PREPARE 管线（只到确认页/提交前，不 Commit）
- **PHASE 7 完成（Controlled Execution）**：Policy Engine + Kill Switch + Compensation + 受控执行管线（§37 事务语义）；默认 default_deny，真实执行需显式放行 + 审批 + executor（§56/§66）
- 测试：`tests/` 下 234 项全部通过，含 **Jarvis Host Swap Test（§46/§73）**、**CareerPilot Migration Test（§64/§65）** 与 Replay 测试（§47）。

## 快速开始

```bash
# venv 已含 pydantic v2 + pytest + scrapling（Python 3.12）
../.venv/bin/python -m pytest -q        # 跑全部测试（234 项）

# 端到端 Shadow Scan（Queenstown Top5 推荐，fixture 回放，不联网）
../.venv/bin/python -m universal_agent.apps.shadow_scan \
    --task tasks/queenstown-travel-watch.yaml \
    --fixtures tests/replay/fixtures --sources ctrip,fliggy

# 接入真实 Skyscanner（浏览器抓取，需本机 Chrome；较慢，Tier2 验证用）
../.venv/bin/python -m universal_agent.apps.shadow_scan --live --max-queries 3

# 综合 CLI：多域一站式（flight/hotel/jobs/bundle/prepare/execute）
../.venv/bin/python -m universal_agent.apps.agent_cli --domain bundle

# 定时调度守护：按基线时间自动扫描 watch 任务（§15/§60）
../.venv/bin/python -m universal_agent.apps.scheduler \
    --tasks-dir tasks --data-dir data --tick 60 --domain flight
```

## 路线图

- **全部 8 个 Phase 完成**（0–7，233 测试全绿）。真实执行默认 DENY，需人工 policy 放行 + 审批 + executor 才可能（§56/§66 边界保持）
- 后续（可选增强）：PREPARE/EXECUTE 接真实 Skill / Policy 管理界面 / Kill Switch 审计联动
