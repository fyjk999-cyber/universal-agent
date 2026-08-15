# Universal Agent — Roadmap

> 版本路线（对齐 SPAC.md 与 FINAL_VERIFICATION_REPORT.md）· 重写：2026-08-14（v1.0 验收后）

## 当前版本状态

**v1.0 完成 — FINAL VERIFICATION ACCEPTED（2026-08-14）**

- **514 tests / 0 failed**（`cd universal-agent && ../.venv/bin/python -m pytest -q` 复核通过）
- `agent-project-test` 全量验收 **TEST A–J 全 PASS**（PASS 10 ｜ FAIL 0 ｜ PARTIAL 0 ｜ UNVERIFIABLE 0）→ **ACCEPTED**（该验收覆盖 Core 冒烟/生命周期/安全边界）
- ⚠️ **2026-08-15 深度代码审计修正（`MISSING_FEATURE_REPORT.md`）**：TEST A–J 未覆盖的 SPAC 硬性点存在 **6 项 P0**（FR-030/031/032/033 Harness 集成 + RULE-003 SQLite 接线违规 + 多源 DoD 未满足）与 15 项 P1，v1.0 验收的"28 项 Final Acceptance Criteria 全部满足"结论**过高**，实际达成度见下表 Chapter 完成度。**PROJECT_STATUS = DEVELOPMENT**（未达 SPAC §53 Definition of Done：Notify/Approve 未真实送达、多源未达标）。

## 版本历史（依据各 SPRINT_REPORT）

| 版本 | 内容 | 测试 | 状态 |
|---|---|---|---|
| v0.3 | 早期 Shadow Runtime 骨架：8 Phase 架构原型 + 核心契约雏形 | 239 | ✅ 完成 |
| v0.4 | **P0 Correctness Hardening**（SPRINT A + A.1）：IANA 时区/misfire、ScanRun 独立状态+backoff、Slippage(approved vs actual)、Compensation 成功路径、Idempotency reserve/finalize/reconcile、Skyscanner fail-closed、Flight Entity Resolution、Ranking Eligibility Gate、Approval Snapshot、单一 L3/L4 执行路径 | 376 | ✅ 完成 |
| v0.5 | **SQLite Runtime Unification**（P1 + P1.1）：Repository Protocol、单一 Runtime Truth、RunLease DB 互斥、Host 命令边界（TaskCoordinator/StateMachine）、External-call UNKNOWN→reconcile 三分支 | 401 | ✅ 完成 |
| v0.6 | **Reliable Events**（P2）：SQLite EventStore + Transactional Outbox + Dispatcher + Retry + DLQ；EventEnvelope 补 correlation/causation/run_id；业务状态与 outbox 同事务 | 409 | ✅ 完成 |
| v0.7 | **Memory + Observability**（P3 + P4）：Memory 8 子域（intent/preference/decision/observation/answer/task_state/policy/execution_history）+ Metrics/Traces/StructuredLogs | 436 | ✅ 完成 |
| v0.8 | **Skill + Source 基础设施 + Flight Live**（P5–P8）：SkillProtocol + CapabilityResolver、SourceHealthTracker + ResourceGovernor、RuleAdaptiveScheduler（时间窗口频率）、Skyscanner Live 垂直闭环 | 459 | ✅ 完成 |
| v0.9 | **Hotel + Travel Bundle**（P9 + P10）：HotelPolicy 归一化（breakfast/cancellation/tax/occupancy，未知=UNKNOWN）、Bundle 总效用非贪心 | 468 | ✅ 完成 |
| v0.10 | **Opportunity + Preference**（P11 + P12）：Opportunity availability/trend（estimate 标记）、versioned/explainable/reversible PreferenceLearner（不碰 Policy） | 476 | ✅ 完成 |
| v0.11 | **CareerPilot / Jobs**（P13）：JobSkillProtocol、human-only gate、Answer Memory；第二 Domain 验证 Core 通用性（**零 Core 修改**） | 480 | ✅ 完成 |
| v0.12 | **Security**（P14）：CredentialVault（混淆存储，明文不落盘）+ PermissionManager（默认拒绝） | 484 | ✅ 完成 |
| v0.13 | **Action 链路**（P15 + P16）：L2 PREPARE（flight/jobs/ecommerce，No Commit）+ Controlled Actions 全链验证（KillSwitch/Idempotency/Slippage/Compensation/Audit） | 496 | ✅ 完成 |
| v0.14 | **新 Domain**（P17–19）：Railway/Ecommerce/Food Raw 契约 + normalize + entity_key（复用既有 Core，零 Core 修改） | 500 | ✅ 完成 |
| v0.15 | **Jarvis + CI**（P20 + P21/22）：Jarvis Host Swap 全链路（Core 零修改）；GitHub Actions（3.11/3.12）+ 依赖组可复现安装 | 504 | ✅ 完成 |
| **v1.0** | **FINAL VERIFICATION**：TEST A–J 全 PASS，28 项 Final Acceptance Criteria 全满足 | **514** | ✅ 完成（2026-08-14） |

## SPAC Chapter 0–9 完成度（依据实际代码 + 测试，2026-08-14 复核）

| Chapter | 名称 | 完成度 | 依据 |
|---|---|---|---|
| CHAPTER 0 | Repository Reality Lock | **COMPLETE** | `scanner/ tasks/` 已归档至 `legacy/`；SPAC.md 建立；README/ROADMAP/KNOWN_LIMITATIONS/FINAL_VERIFICATION 与代码对齐（本文件重写即完成 0.3）；MISSING_FEATURE_REPORT 由架构审计跟踪 |
| CHAPTER 1 | Runtime Composition | **PARTIAL** | SQLite schema 全表存在（`persistence/sqlite.py`），但 `service.py:37-42` RepositorySet 仅接 tasks/scan_runs/memory；**events/outbox/observations/notifications/approvals/actions/audit/source_health 的 9 个 SQLite repo 定义但零装配（仅测试实例化）**；运行期 approvals/idempotency/dedup/observations 仍为 JSON（RULE-003 违规，P0）；OutboxDispatcher 未接线（2026-08-15 深度审计修正，原"COMPLETE"过高） |
| CHAPTER 2 | DeepSeek Harness Production Integration | **PARTIAL** | 2.2 事件/2.3 审批/2.6 重启恢复有实现；但 **FR-030 `run_task_once()` 仍 `not_implemented`、FR-031 通知仅写日志、FR-032 审批固定返回 pending、FR-033 DSH Bridge 硬编码 `/Users/...`**（代码证据见 FINAL_VERIFICATION_REPORT「已披露缺口」表，P1 级，2026-08-15 审计确认） |
| CHAPTER 3 | Generic Source Runtime | **PARTIAL** | 3.5 CapabilityResolver ✅（P5）、3.6 Source Health ✅（P6）、3.7 Failure Isolation ✅（TEST I）；**3.1 HTTP / 3.2 API / 3.3 Browser / 3.4 Mobile 均为空占位**（`adapters/{http,api,browser,mobile}/` 仅 `__init__.py`） |
| CHAPTER 4 | Travel Multi-Source | **PARTIAL** | 4.1 Skyscanner hardening ✅（P8，唯一 Flight Live 源）；**4.2/4.3 第二/第三 Flight Source（Ctrip/Fliggy/Tongcheng）未接（FR-074）、4.4 Hotel Live Source 未接（仅 replay）、4.5 单源下无法做 cross-source entity resolution、4.7 Live Bundle 依赖单 Flight 源 + replay Hotel** |
| CHAPTER 5 | Persistent Opportunity Watch | **COMPLETE** | 5.1 Historical Baseline/percentile ✅（`opportunity/engine.py` 基于 quotes 历史）、5.2 Price History ✅、5.3 Trend estimate ✅（P11，is_estimate=true）、5.4 Opportunity Score ✅、5.5 ConditionWatch ✅、5.6 Notification Cooldown ✅（dedup 持久化）、5.7 Deadline-sensitive 频率 ✅（P7 RuleAdaptiveScheduler 时间窗口） |
| CHAPTER 6 | Jobs Productization | **PARTIAL** | 6.2 Job Pipeline / 6.4 Answer Memory / 6.5 Human-only / 6.6 Prepare ✅（P13/P15）；**6.1 Live Source 未接**（官方/LinkedIn/SEEK 仅 `JobSkillProtocol`，无真实适配器） |
| CHAPTER 7 | Additional Domains | **PARTIAL** | P17–19 完成 **Raw 契约 + normalize + entity_key**；Constraint/Score/Skill/Source/Verify/Watch/Notification 每域未完成（Railway FR-110~117 等未全达成） |
| CHAPTER 8 | Controlled Execution Productionization | **PARTIAL** | 8.4 Approval Lifecycle / 8.5 L3 / 8.6 L4 / 8.7 Reconcile / 8.8 Compensation / 8.9 KillSwitch ✅（P15/P16）；**8.1 生产凭据后端未做（CredentialVault 为 dev 混淆，FR-191/192）、8.2 IdentityVault / 8.3 SessionBroker 空占位**（FR-193/194） |
| CHAPTER 9 | Jarvis Ready | **COMPLETE** | P20 Host Swap 全链路验证：Harness 断开 → Jarvis 接入 → Task/Memory 状态继续（同一 SQLite），全 HostProtocol 方法验证，**Core 零修改**（TEST H） |

**结论（2026-08-15 深度审计修正）：仅 CH 0（Reality Lock）、CH 5（Opportunity Watch）、CH 9（Jarvis Ready）COMPLETE；CH 1（Runtime 接线）、CH 2（Harness 生产集成）、CH 3（通用 Adapter）、CH 4（Travel 多源）、CH 6（Jobs）、CH 7（新 Domain）、CH 8（受控执行生产化）均为 PARTIAL——P0×6 / P1×15 全部列入下一阶段路线（v1.1）。**

## 下一阶段路线（v1.1+）

> 来源：FINAL_VERIFICATION_REPORT「遗留限制」+ 本文件 Chapter 完成度 + 代码审计缺口。
> 优先级：P0 = 必修（安全/正确性）· P1 = 高 · P2 = 中 · P3 = 低。

### v1.1 — 生产化硬缺口（P0/P1）

| # | 工作项 | 对应 FR | 优先级 | 目标 |
|---|---|---|---|---|
| 1 | **CHAPTER 2 补齐（Harness 生产集成）**：真实 `run_task_once()`（含修正 test_host_swap 固化断言）；通知真实送达（非仅日志）；审批流程真实流转（非固定 pending） | FR-030 / FR-031 / FR-032 | **P0** | CHAPTER 2 Gate PASS（SPAC §36） |
| 2 | **DSH Bridge 可移植配置**：移除 `/Users/...` 硬编码，接 `UA_ROOT / UA_PYTHON / UA_DATA_DIR / UA_CONFIG`，禁止 silent fallback | FR-033 | **P0** | 换机器零改代码 |
| 3 | **RULE-003 运行时接线（CH1 补齐）**：approvals/idempotency/dedup/observations/ks 全部切换到 SQLite RepositorySet（9 个 repo 装配进 `service.py`），JSON 仅保留 Export/Debug/Log | RULE-003 / CH1-1.1 | **P0** | 无第二可写真相 |
| 4 | **多源 DoD 起步**：第二 Flight Live Source（Ctrip/Fliggy）+ Hotel Live Source | FR-074 / FR-082 | **P0**（DoD 多源） | Flight+Hotel 真实多源 |
| 5 | **生产凭据后端（macOS 优先）**：CredentialVault 接 OS Keychain（Security Framework），dev 混淆降级为兜底 | FR-191 | **P0**（安全） | 明文/混淆 key 不落盘 |
| 6 | **通用 Adapter 层落地**：HTTP Adapter + API Adapter + Browser Adapter（含深度、失败隔离） | FR-060 / FR-061 / FR-062 | P1 | CH 3.1/3.2/3.3 Gate |
| 7 | **Jobs Live Source**（官方 Careers / LinkedIn / SEEK 之一，走 JobSkillProtocol） | FR-100 / FR-101 | P1 | CH 6.1 Gate |

### v1.2 — 多源与安全完整化（P1/P2）

| # | 工作项 | 对应 FR | 优先级 |
|---|---|---|---|
| 8 | 第三 Flight Live Source（Tongcheng） | FR-074（CH 4.3） | P1 |
| 9 | Cross-source Flight/Hotel Entity Resolution（跨平台合并验证） | FR-071 / FR-081（CH 4.5） | P1 |
| 10 | Identity Vault + Session Broker（独立于普通 Memory、外部平台 Session 管理） | FR-193 / FR-194（CH 8.2/8.3） | P1 |
| 11 | Windows Credential Manager 生产后端 | FR-192 | P1 |
| 12 | Railway / Ecommerce / Food 各域 Live Skill（Raw→Normalize→Entity→Score→Skill→Verify→Watch） | FR-110~117 等（CH 7） | P2 |
| 13 | Skyscanner 详情页补齐：duration-only PARTIAL → STRUCTURED（detail/verify/availability 接真实详情页） | FR-073 / FR-052 / FR-053 | P2 |
| 14 | Notification priority/channel 完整化（LOW/NORMAL/HIGH/URGENT + Harness/Desktop/Mobile/Webhook/Jarvis 抽象） | FR-162 / FR-163 | P2 |

### v1.3+ — 终态与增强（P2/P3）

| # | 工作项 | 对应 FR | 优先级 |
|---|---|---|---|
| 15 | **Mobile Adapter Protocol 扩展**（第一阶段仅定义 Protocol/Contract，不接真实移动端） | FR-063（CH 3.4） | P2 |
| 16 | **DSH Bridge 可移植性终态 + Jarvis 生产部署**（Jarvis capabilities：voice/desktop/mobile/approval/memory/watch/action/health） | FR-033 终态 / FR-041 | P2 |
| 17 | RunLease heartbeat 后台线程 + Outbox Dispatcher 接入 daemon 后台循环（当前拉模式） | FR-014 / FR-021 | P2 |
| 18 | Tier3 官方源真实航司验证适配器（公开价格查询页，不登录/不购买） | FR-052 Tier3 | P2 |
| 19 | 多用户隔离（PreferenceLearner 当前固定 u1）+ 趋势加权学习 | FR-150 / FR-152 | P3 |
| 20 | Metrics 全链路自动埋点；traces 父子 span 关联；可选 OpenTelemetry 导出 | FR-31（Observability） | P3 |

## 禁止项（当前阶段）

- **禁止放行真实支付 / 自动执行**：L4 高风险操作保持 DEFAULT DENY（RULE-008），直到 Policy + Approval + Snapshot + Slippage + Idempotency 全链在真实源上验证通过（FR-173）。
- **禁止绕过平台安全机制**：不绕过验证码、不登录态自动购买、不自研浏览器引擎（SPAC §33 Non-Goals）。
- **禁止 LLM 进入核心确定性链**：Filter/Dedup/Normalize/Entity/Score/Rank/Policy 必须程序化（RULE-005）；LLM 只辅助 intent/explain/summary/preference。
- **禁止第二套 Runtime State**：SQLite 是唯一事实源（RULE-003）；JSON 仅用于 Export/Debug/Log/Snapshot。
- **禁止 Host 直改 Repository**：一切 WatchTask 状态修改必须经 TaskCoordinator → StateMachine（RULE-004）。
- **禁止新 Domain 重写 Core**：新增能力只允许在 `domains/<domain> / skills/<source> / contracts/raw`（RULE-002 / SPAC §15）。
- **禁止无测试实现**：每个修复/新功能先写失败测试（RED）再实现（GREEN），回归必须 0 failed。
- **禁止并行小章节测试冲刺**：SPAC §45，小章节顺序、可重复、可定位失败（SUBCHAPTER_PARALLEL_TESTING = FALSE）。
