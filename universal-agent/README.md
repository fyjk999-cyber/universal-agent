# Universal Persistent Watch & Decision Agent

**Host-Agnostic + Contract-First + Event-Driven + Replaceable**

长期存在的个人监控与决策基础设施，不是单一搜索 Agent。产品与架构 Source of Truth 见仓库根 [`SPAC.md`](../SPAC.md)。

```text
REMEMBER → WATCH → OBSERVE → NORMALIZE → COMPARE → VERIFY → DECIDE
    → NOTIFY → PREPARE → APPROVE → ACT → VERIFY ACTION → LEARN → REMEMBER
```

支持 Domain：`Flight / Hotel / Travel / Jobs / Railway / Ecommerce / Food / Future`
支持任务：`OneShot / Scheduled / Watch / ConditionWatch / Composite / MultiDomain`

## 当前状态（v1.0）

- **v1.0 FINAL VERIFICATION ACCEPTED（2026-08-14）**：**514 tests / 0 failed**，`agent-project-test` 验收 TEST A–J 全 PASS（见 [`docs/FINAL_VERIFICATION_REPORT.md`](docs/FINAL_VERIFICATION_REPORT.md)）。
- ⚠️ **2026-08-15 深度代码审计（[`MISSING_FEATURE_REPORT.md`](../MISSING_FEATURE_REPORT.md)）**：TEST A–J 未覆盖的 SPAC 硬性点存在 **6×P0 + 15×P1**（FR-030~033 Harness 集成、RULE-003 SQLite 接线、多源 DoD、Decision 层等），**PROJECT_STATUS = DEVELOPMENT**（未达 SPAC §53 DoD）；修复路线见 [`docs/ROADMAP.md`](docs/ROADMAP.md) v1.1。
- 已完成 Sprint：P0 Correctness Hardening（A/A1）→ SQLite Runtime Unification（P1.1）→ Reliable Events/Outbox/DLQ（P2）→ Memory 8 子域（P3）→ Observability（P4）→ Skill Runtime（P5）→ Source Health/Governor（P6）→ Adapters（P7）→ Skyscanner 真源（P8）→ Hotel（P9）→ Travel Bundle（P10）→ Opportunity（P11）→ Preference Learning（P12）→ Jobs/CareerPilot（P13）→ CredentialVault（P14）→ L2 Prepare（P15）→ Controlled Actions + KillSwitch（P16）→ Railway/Ecommerce/Food Domains（P17–19）→ Jarvis Host Swap（P20）→ CI Gates + Reproducibility（P21/22）。
- SPAC Chapter 完成度与能力明细见 [`docs/ROADMAP.md`](docs/ROADMAP.md)、[`docs/CAPABILITY_MATRIX.md`](docs/CAPABILITY_MATRIX.md)、[`docs/KNOWN_LIMITATIONS.md`](docs/KNOWN_LIMITATIONS.md)。

## 架构（核心铁律，SPAC §4）

```text
DeepSeek Harness (当前 Host)          Jarvis (未来 Host)
        ↓                                   ↓
HarnessHostAdapter                  JarvisHostAdapter
        ↓                                   ↓
                        HostProtocol
                                ↓
                    Universal Agent (本包，与 Host 无关)
```

- **RULE-001**：Core 不依赖任何 Host（当前是 DeepSeek Harness）。依赖方向只能是 Host → HostAdapter → HostProtocol → Universal Agent。
- **RULE-002**：未来 Jarvis 接入只新增 `JarvisHostAdapter`，禁止重构 Core/Memory/Domain/Skill/Watch/Scheduler/Action Gateway（**ZERO CORE REWRITE**）。
- **RULE-003**：SQLite 是 Runtime State 唯一事实源（tasks/scan_runs/events/outbox/memory/notifications/approvals/actions/audit/source_health）；JSON 只用于 Export/Debug/Log。
- **RULE-004**：所有 WatchTask 状态修改必须经过 TaskCoordinator → StateMachine → TaskRepository；Host 不允许直接改 Repository。
- **RULE-005**：Filter/Dedup/Normalize/Entity Resolution/Constraint/Score/Rank/Change Detection/Policy 程序化，LLM 不得成为唯一实现。
- **RULE-006**：Observation ≠ Evidence ≠ Decision；Decision 必须基于 Evidence，禁止"LLM 认为价格是 X"直接成为事实。
- **RULE-007/008**：一切外部副作用必须经过 ActionGateway；高风险操作 DEFAULT = DENY，只有 Policy + Approval 满足才允许。
- **RULE-009**：Fail Closed——PARTIAL/UNKNOWN/UNVERIFIED 不得脑补为完整数据。
- **RULE-010**：所有重要行为 Traceable / Replayable / Explainable / Recoverable。

## 目录速览

```text
universal_agent/
├── core/                  # contracts(冻结契约) / normalization / evidence / verification
│                          # scoring / ranking / constraints / decision / opportunity
│                          # change_detection / bundling / state_machine(Watch 状态机)
├── persistence/           # SQLite RepositorySet（唯一 Runtime Truth）
├── events/                # EventEnvelope + EventStore + Transactional Outbox + Dispatcher + DLQ
├── coordinator/           # scheduler(时区/misfire/retry/lease) / watch_manager / task_registry
│                          # scanner / source_planner / query_planner / checkpoint / deadline
│                          # dedup / intent / priority / resources / trigger_engine
├── hosts/protocol/        # HostProtocol（Core 唯一允许依赖的 Host 面）
├── hosts/deepseek_harness/# 当前 Host 适配器
├── hosts/jarvis/          # 未来 Host 适配器（Host Swap 已验证，Core 零修改）
├── domains/               # flight / hotel / travel / jobs / railway / ecommerce / food
├── memory/                # intent / preferences / decisions / observations / answers
│                          # task_state / policy / execution_history（scope+confidence+版本化）
├── actions/               # gateway / policy / approval / idempotency / slippage / compensation
├── security/              # credential_vault / identity_vault / session_broker / permissions
├── notifications/         # 持久化去重（fingerprint + cooldown）+ priority + channel
├── observability/         # audit / logs / metrics / traces
├── registry/              # skills / capabilities / health / marketplaces
├── adapters/              # skyscanner / http / api / browser / mobile / official / replay / fx
├── apps/                  # shadow_scan / agent_cli / scheduler
└── dsh/                   # DeepSeek Harness Bridge（uabrg-plugin.js）
```

## 快速开始

```bash
# venv 已含 pydantic v2 + pytest + scrapling（Python 3.12）
cd universal-agent
../.venv/bin/python -m pytest -q        # 跑全部测试（514 项，全绿）

# 端到端 Shadow Scan（Queenstown Top5 推荐，fixture 回放，不联网）
../.venv/bin/python -m universal_agent.apps.shadow_scan \
    --task tasks/queenstown-travel-watch.yaml \
    --fixtures tests/replay/fixtures --sources ctrip,fliggy

# 接入真实 Skyscanner（浏览器抓取，需本机 Chrome；较慢，Tier2 验证用）
../.venv/bin/python -m universal_agent.apps.shadow_scan --live --max-queries 3

# 综合 CLI：多域一站式（flight/hotel/jobs/bundle/prepare/execute）
../.venv/bin/python -m universal_agent.apps.agent_cli --domain bundle

# 定时调度守护：按基线时间自动扫描 watch 任务（SQLite 持久化 + RunLease）
../.venv/bin/python -m universal_agent.apps.scheduler \
    --tasks-dir tasks --data-dir data --tick 60 --domain flight
```

## DeepSeek Harness Bridge（当前 Host）

- 插件：`dsh/uabrg-plugin.js`（安装/卸载/reload/healthcheck、任务命令、通知、审批入口）。
- Watch 长期存活由 SQLite + Scheduler 保证（§FR-034：Harness 重启不丢 Watch），不依赖临时 Plugin Timer。
- 配置可移植：`UA_ROOT / UA_PYTHON / UA_DATA_DIR / UA_CONFIG`（§FR-033），禁止回退到开发者机器路径。

## 文档索引

| 文档 | 内容 |
|---|---|
| [`SPAC.md`](../SPAC.md) | 产品 + 架构 + 功能需求 Source of Truth（FR/RULE/CHAPTER） |
| [`docs/CAPABILITY_MATRIX.md`](docs/CAPABILITY_MATRIX.md) | 能力矩阵（代码实测） |
| [`docs/API_SOURCES.md`](docs/API_SOURCES.md) | 真实数据源接入指南（Kiwi Tequila / Ctrip / Booking 端点配置） |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | 版本路线 + SPAC Chapter 完成度 + 下一阶段 |
| [`docs/KNOWN_LIMITATIONS.md`](docs/KNOWN_LIMITATIONS.md) | 已知限制（已解决/当前/设计边界） |
| [`docs/FINAL_VERIFICATION_REPORT.md`](docs/FINAL_VERIFICATION_REPORT.md) | v1.0 最终验收报告 |
| [`../MISSING_FEATURE_REPORT.md`](../MISSING_FEATURE_REPORT.md) | SPAC vs 实际代码差距报告（SPAC §49） |
| [`../legacy/README.md`](../legacy/README.md) | 早期原型归档（DO NOT EXTEND，SPAC §32） |
