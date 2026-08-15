# MISSING_FEATURE_REPORT.md — SPAC vs ACTUAL CODE 差距审计

> 审计日期：2026-08-15 · 审计方式：只读代码审计（未修改任何代码文件）
> 依据：`SPAC.md`（唯一权威，FR-001~FR-194、RULE-001~010、Chapter 0-9）+ `universal-agent/universal_agent/`（190 py 文件）+ `universal-agent/tests/`（90 文件，pytest 收集 514 tests 通过）
> 判定标准：PASS=实现+测试覆盖；PARTIAL=骨架/部分实现（字段缺失、仅一个 Live Source、Mock/Stub、仅 Protocol、未接线）；NOT_IMPLEMENTED=无对应代码；FAIL=有代码但与 SPAC 要求矛盾；BLOCKED=被其他未完成项阻塞。
> 证据原则：所有判定以实际代码文件:行号为准，不信任文档/README 声明。

---

## ✅ P23 修复状态（2026-08-15，同日修复）

> 本报告原始审计为 P0 基线。以下 5 项 P0 已于同日（P23 Sprint）RED→GREEN 修复，
> 测试基线 514 → **532 passed / 0 failed**。原始条目保留在 §3 供追溯。

| P0 条目 | 修复内容 | 验证 |
|---|---|---|
| FR-030 run_task_once 桩 | 新增 `coordinator/run_once.py`（run_once/run_once_async + ScanRun 记录）；Harness/Jarvis 双适配器实现；`test_host_swap.py:86` 固化断言已修正 | `tests/unit/test_p23_run_once.py` 4 项 |
| FR-031 通知仅日志 | 通知持久化 SQLite（`SqliteNotificationRepository`）+ `notification_sink` 投递通道 + ShadowScanCoordinator `notifier` 接线 + FR-164 事件类型（PRICE_DROP/RARE_OPPORTUNITY/AVAILABILITY_CHANGE/WATCH_FAILED/APPROVAL_REQUIRED/ACTION_RESULT） | 3 项 |
| FR-032 审批固定 pending | `ApprovalInbox` 支持 SQLite 后端（RULE-003）；host `request_approval` 真实创建 + 新增 `decide_approval`（APPROVED/REJECTED 持久化）；`agent_cli --approve <id> --decision yes/no` 入口 | 7 项 |
| FR-033 DSH 硬编码路径 | `dsh/uabrg-plugin.js` 路径解析：Plugin Config → `UA_ROOT/UA_PYTHON/UA_DATA_DIR/UA_CONFIG` → Auto Discovery → Explicit Failure（零硬编码） | grep 验证无 `/Users/` |
| RULE-003 JSON 双写 | `RepositorySet` 全量接线（tasks/scan_runs/memory/events/outbox/observations/notifications/approvals/actions/audit/source_health + 3 个 Kv 表）；IdempotencyStore/NotificationDedup/KillSwitch 支持 SQLite 后端（跨重启保持） | 4 项 |

**剩余 P0（1 项，属 CHAPTER 4）**：多源 DoD（FR-074 第二/三 Flight 源 + FR-082 Hotel Live 源）。

## 🚀 CH4 多源起步（2026-08-15 同日）

| 原缺口 | 现状（代码实现 + 测试） | 剩余 |
|---|---|---|
| FR-060 HTTP Adapter 空占位 | ✅ `adapters/http/adapter.py`（超时/重试/失败隔离，HttpAdapterError） | — |
| FR-074 仅 Skyscanner 单源 | ✅ **第二 Flight 源** `adapters/ctrip/`（CtripFlightSkill，SkillProtocol + HTTP JSON，fail-closed；健康检查显式 UNAVAILABLE/AUTH_REQUIRED）；scheduler 接线（UA_CTRIP_ENDPOINT） | 真实端点验证（需 key/端点）、第三源、跨源实体解析 |
| FR-082 Hotel 无 Live 源 | ✅ **Hotel 源** `adapters/booking/`（BookingHotelSkill，同上模式） | 真实端点验证（UA_BOOKING_ENDPOINT） |
| FR-064 失败隔离 | ✅ 测试锁定：源不可达 → UNAVAILABLE，整体 Task 仍完成 | — |
| FR-056 Skill 不执行 | ✅ prepare_action 拒绝（测试锁定） | — |

验证：`tests/integration/test_ch4_multi_source.py` 5 项（本地 HTTP 服务器全链路：HTTP→JSON→RawListing/RawHotel→Normalize→候选）。测试基线 **538 passed / 0 failed**。

---

## 0. 总体结论

共审计 **89 个 FR**（FR-001~FR-194 中实际定义的条目）与 RULE-001~010、Chapter 0-9。

| 判定 | 数量 | 占比 |
|---|---|---|
| **PASS**（实现 + 测试覆盖） | 35 | 39.3% |
| **PARTIAL**（部分实现 / Mock / Stub / 单 Live 源 / 未接线） | 29 | 32.6% |
| **NOT_IMPLEMENTED**（无对应代码） | 23 | 25.8% |
| **FAIL**（与 SPAC 明确矛盾） | 2 | 2.2% |
| **BLOCKED** | 0 | 0% |

**P0 问题（6 项，全部对应 SPAC 硬性点）**：

1. **FR-030 `run_task_once()` 仍为 `not_implemented` 桩**（Harness+Jarvis 双适配器），SPAC 明文"不得保留"。
2. **FR-031 Harness 通知从不真实送达**：`send_notification` 只写日志；事件止于进程内 bus（`events/handlers/` 空），生产零调用 host 通知。
3. **FR-032 审批无法被真实用户决策**：host `request_approval` 固定返回 pending；`ApprovalInbox.decide()` 生产零调用（无 UI/API/CLI 入口），"User Decision→恢复管线"断链。
4. **FR-033 DSH Bridge 硬编码 `/Users/huhongjie/...`** 双路径，零环境变量/自动发现/显式失败。
5. **RULE-003 运行时违规**：approvals.json / idempotency.json / ks.json / 通知 dedup JSON / observations.json 仍是第二可写真相；对应 SQLite Repository 全部定义但零装配（`service.py` RepositorySet 仅接 tasks/scan_runs/memory）。
6. **FR-082 Hotel 无任何 Live Source**（booking 仅 replay fixture）；FR-074 Flight 也仅 Skyscanner 一个真实 Live 源——不满足 DoD"至少 Flight + Hotel 具有真实多 Source Pipeline"。

---

## 1. Chapter 0-9 完成度表

| Chapter | 名称 | 完成度 | 关键证据 |
|---|---|---|---|
| CHAPTER 0 | Repository Reality Lock | **COMPLETE** | 根目录旧 `scanner/ tasks/` 已归档至 `legacy/`；SPAC.md 建立；README/ROADMAP/KNOWN_LIMITATIONS/FINAL_VERIFICATION 与代码对齐；514 tests 收集通过（本报告即 0.5 产物） |
| CHAPTER 1 | Runtime Composition | **PARTIAL** | SQLite schema 全表存在（`persistence/sqlite.py`），但 RepositorySet 仅接 tasks/scan_runs/memory（`service.py:37-42`）；events/outbox/observations/notifications/approvals/actions/audit/source_health 的 9 个 SQLite repo 零装配（仅测试实例化）；OutboxDispatcher 未接线；运行期 approvals/idempotency/observations 仍为 JSON |
| CHAPTER 2 | DeepSeek Harness Production Integration | **PARTIAL**（最大缺口） | FR-030/031/032/033 全部未达标（P0）：run_task_once 桩、通知仅日志、审批固定 pending、DSH 桥硬编码；2.5/2.6 有部分实现 |
| CHAPTER 3 | Generic Source Runtime | **PARTIAL** | 3.5 CapabilityResolver（P5）、3.6 Source Health（P6）、3.7 Failure Isolation（TEST）完成；**3.1 HTTP / 3.2 API / 3.3 Browser / 3.4 Mobile 全为空目录**（0 字节 `__init__.py`） |
| CHAPTER 4 | Travel Multi-Source | **PARTIAL** | 4.1 Skyscanner hardening 完成（唯一 Flight Live 源）；**4.2/4.3 第二/第三 Flight Source 未接（ctrip/fliggy 仅 replay fixture）、4.4 Hotel Live Source 未接（booking 仅 fixture）、4.5 无真实 cross-source resolution、4.7 Live Bundle 缺酒店真源** |
| CHAPTER 5 | Persistent Opportunity Watch | **COMPLETE** | OpportunityScore（`core/opportunity/engine.py`）、Condition Watch 已接线（`scanner/shadow.py:_maybe_notify`）、dedup cooldown、RuleAdaptiveScheduler 时间窗口频率均有实现+测试 |
| CHAPTER 6 | Jobs Productization | **PARTIAL** | 6.2 管线/6.4 Answer Memory 存储/6.5 Human-only 函数/6.6 Prepare 有实现；**6.1 Live Source 未接、6.3 Application State 状态机不存在（FR-102）、6.4/6.5 未接入产品流程（仅函数+测试）** |
| CHAPTER 7 | Additional Domains | **PARTIAL** | Railway/Ecommerce/Food 仅 Raw 契约+normalize+entity_key（P17-19）；每域缺 Scoring/Skill/Source/Verify/Watch/Notification，**无 RAILWAY_LIVE_READY/ECOMMERCE_LIVE_READY/FOOD_LIVE_READY 声明** |
| CHAPTER 8 | Controlled Execution Productionization | **PARTIAL** | 8.4-8.9 机制完成（Approval/Snapshot/Idempotency/Slippage/Reconcile/Compensation/KillSwitch 实现+测试）；**但 L2/L3/L4 主网关硬禁（`gateway.py:28`）、8.1 生产凭据后端（Keychain/Credential Manager）未实现、8.2 IdentityVault / 8.3 SessionBroker 空占位** |
| CHAPTER 9 | Jarvis Ready | **COMPLETE** | Mock adapter + Host Swap 全链路测试（`test_host_swap.py`、`test_p20_jarvis.py`），Core 零修改；SPAC §11 允许当前保留 Mock/Preview Adapter |

---

## 2. RULE-001~010 合规表

| Rule | 判定 | 证据 |
|---|---|---|
| RULE-001 Host Independence | **PASS** | `core/` 永不 import hosts/*（`core/__init__.py` 声明；grep 零命中）；依赖方向 Host→HostAdapter→HostProtocol→UA |
| RULE-002 Jarvis Replaceability | **PASS** | `hosts/jarvis/adapter.py` 仅实现 HostProtocol；装配在组合根 `service.py:63-70` 切换；`test_host_swap.py` 证明同 SQLite 换 Host 后 Task/Memory 继续 |
| RULE-003 SQLite Runtime Truth | **FAIL** | 任务/scanrun 已唯一化到 SQLite（`daemon.py:278-280`），但 `actions/approval/inbox.py:24`（approvals.json）、`actions/idempotency/store.py:36`（idempotency.json）、`actions/policy/killswitch.py:18`（ks.json）、`notifications/dedup.py:42-48`（dedup JSON）、`memory/observations/store.py`（observations.json）在运行时仍是第二可写真相；对应 SQLite repo（`persistence/repos.py` 9 个类）零装配 |
| RULE-004 Host 不直接改 Repository | **PARTIAL** | Host 侧合规：两个 adapter 全部委托 TaskCoordinator 命令（`adapter.py:30-54`、jarvis `adapter.py:31-55`），apply_update 经 `can_transition`（`task_coordinator.py:81-89`）；**Core 侧绕过：`WatchDaemon._advance` 直接 `registry.update`（`daemon.py:260`）、`_mark_watch_failed` 直接置 FAILED 绕过 transition()（`daemon.py:247`）** |
| RULE-005 Deterministic Core | **PASS** | Normalize/Scoring/Rank/Verify/Opportunity/Trigger 全部程序化确定性实现（无 LLM 调用代码）；LLM 仅辅助意图/解释 |
| RULE-006 Observation/Evidence/Decision 分离 | **PARTIAL** | Observation（`contracts/observation.py`）+ Evidence（`core/verification/verifier.py` 产出）真实；**Decision 层缺失**：`core/decision/` 空目录，无 Decision 契约，无 supporting_evidence（FR-132 NOT_IMPLEMENTED） |
| RULE-007 External Side Effects | **PASS** | Domain/Skill 只构建 ActionPlan 从不执行（`domains/jobs/action.py:3-5`）；执行全部收敛于 `actions/gateway/`；SkillProtocol 无 execute_action（FR-056） |
| RULE-008 Default Deny | **PASS** | `PolicyEngine.default_deny = True`（`actions/policy/engine.py:48`）；`tasks/policy.json` 亦 `default_deny: true`；未知 action 抛 PolicyViolation |
| RULE-009 Fail Closed | **PASS** | PARTIAL→仅 preliminary 不进 Final Top5（`test_p09_eligibility.py`）；search 失败返回 []；verify 未知→UNVERIFIED；Governor 未知资源默认拒绝 |
| RULE-010 Traceability | **PARTIAL** | 事件链带 trace_id/correlation_id/causation_id（`events/envelope.py:21-25`）；**AuditLog 无 trace_id 字段**（`observability/audit/audit.py:23-41`），执行审计与扫描事件 trace 链断裂；无 Decision 层可反查 |

---

## 3. 问题条目清单（按 Severity 排序，P0 在前）

---

### 3.1 P0（6 项）

---

**Requirement:** FR-030
**Expected:** HarnessHostAdapter.run_task_once() 必须真正执行一次扫描并返回结果摘要，不得保留 `not_implemented`（SPAC §10 / CH2-2.1）。
**Actual:** `universal_agent/hosts/deepseek_harness/adapter.py:56-57` 返回 `{"task_id": task_id, "status": "not_implemented"}`；Jarvis 同款 `hosts/jarvis/adapter.py:57-58`。全仓库协议路径无任何真实 run-once 实现；单次扫描仅存在于协议之外（`apps/agent_cli.py --domain` 一次性 ShadowScan、`dsh/uabrg-plugin.js:86-88` 调 agent_cli、`apps/shadow_scan.py`）。`tests/migration/test_host_swap.py:86` 甚至把 `not_implemented` 固化为断言。
**Status:** NOT_IMPLEMENTED
**Severity:** P0
**Affected Modules:** hosts/deepseek_harness/adapter.py, hosts/jarvis/adapter.py, coordinator/scheduler, coordinator/scanner, apps/agent_cli.py
**Missing Work:** 实现 run_task_once：按 task_id 加载 WatchTask → RunLease 加锁 → 经 scanner/runner 执行一次 → 写 ScanRun → 返回结构化结果；更新 test_host_swap 断言（RED→GREEN）。
**Recommended Chapter:** CHAPTER 2（2.1）

---

**Requirement:** FR-031
**Expected:** Harness 必须真正接收到 OPPORTUNITY/PRICE_DROP/WATCH_FAILED/APPROVAL_REQUIRED/ACTION_RESULT 通知，"而不是只写日志"（SPAC §10 / CH2-2.2）。
**Actual:** `hosts/deepseek_harness/adapter.py:70-71` `send_notification` 仅 `log.info("HARNESS NOTIFICATION: ...")`，生产代码零调用（仅测试调用 test_p20_jarvis.py:62、test_host_swap.py:70）；通知链路止于进程内 EventBus——`coordinator/scanner/shadow.py:300-305` 发 NOTIFICATION_REQUESTED/SENT 后无任何 handler（`events/handlers/__init__.py` 为 0 字节）；SQLite notifications 表（`persistence/sqlite.py:98-102`）与 `SqliteNotificationRepository`（`persistence/repos.py:162-172`）零装配；DSH 插件 `dsh/uabrg-plugin.js` 是纯 shell 桥，不读取任何通知；`events/types.py:7-56` 缺 PRICE_DROP/WATCH_FAILED/ACTION_RESULT 等事件类型。
**Status:** FAIL
**Severity:** P0
**Affected Modules:** hosts/deepseek_harness/adapter.py, events/handlers/, notifications/, dsh/uabrg-plugin.js, coordinator/scanner/shadow.py
**Missing Work:** ① 定义 PRICE_DROP/WATCH_FAILED/APPROVAL_REQUIRED/ACTION_RESULT 通知事件类型；② 通知持久化到 SQLite + outbox 投递；③ host 侧真实投递（DSH 插件注册通知 sink，扫描结果/机会推送到会话可见）；④ 接线事件 handlers。
**Recommended Chapter:** CHAPTER 2（2.2）

---

**Requirement:** FR-032
**Expected:** 完整审批流程：ActionIntent→Approval Request→Persistence→User Decision→APPROVED/DENIED→Resume Action Pipeline，不得固定返回 pending（SPAC §10 / CH2-2.3）。
**Actual:** 前半段真实：`actions/approval/inbox.py:39-58` request() 持久化 PENDING 到 approvals.json（由 `actions/gateway/prepare.py:101-108` 调用）；`inbox.py:60-72` decide() 可置 APPROVED/REJECTED 且单测通过（`test_action_prepare.py:96`、`test_phase7_execution.py:232` 验证）。但 host `request_approval` 硬编码返回 `{"approved": False, "status": "pending"}`（`adapter.py:73-75`，jarvis 同款 `adapter.py:74-76`）且不触达 inbox；**decide() 生产代码零调用**（仅测试调用），无任何 UI/API/CLI 审批入口；agent_cli 的 _prepare/_execute 只是打印演示（`agent_cli.py:111-148`）。"用户可决 + 决策回写恢复管线"断在最后一环。
**Status:** PARTIAL
**Severity:** P0
**Affected Modules:** actions/approval/inbox.py, hosts/deepseek_harness/adapter.py, actions/gateway/{prepare,execute}.py, apps/agent_cli.py, dsh/uabrg-plugin.js
**Missing Work:** 提供真实审批入口（DSH 工具/命令 approve <id> [approved|denied]）→ 调 ApprovalInbox.decide() → 回写 host adapter → ControlledExecutor/TransactionExecutor 继续执行；host request_approval 返回真实决策而非固定 pending。
**Recommended Chapter:** CHAPTER 2（2.3）

---

**Requirement:** FR-033
**Expected:** 移除硬编码 `/Users/<name>/...`；使用 UA_ROOT/UA_PYTHON/UA_DATA_DIR/UA_CONFIG；配置优先级 Plugin Config→Environment→Auto Discovery→Explicit Failure；禁止 silent fallback 到开发者机器路径（SPAC §10 / CH2-2.4）。
**Actual:** `dsh/uabrg-plugin.js:20-21` 硬编码 `UA_ROOT = '/Users/huhongjie/Desktop/扫描决策类agent/universal-agent'`、`PY = '/Users/huhongjie/Desktop/扫描决策类agent/.venv/bin/python'`。全文无任何 UA_* 环境变量读取、无自动发现、无缺失时显式失败——默认即静默使用开发者路径，换机/换用户即失效。
**Status:** FAIL
**Severity:** P0
**Affected Modules:** dsh/uabrg-plugin.js
**Missing Work:** 插件按 Plugin Config（cordis 配置）→ Environment（UA_ROOT/UA_PYTHON/UA_DATA_DIR/UA_CONFIG）→ Auto Discovery（PATH/常见安装位置）→ Explicit Failure 解析路径；找不到时抛错而非回退；写可移植性测试。
**Recommended Chapter:** CHAPTER 2（2.4）

---

**Requirement:** RULE-003
**Expected:** SQLite 是 Runtime State 的唯一事实源；WatchTask/ScanRun/Memory/Events/Outbox/Notification/Approval/Action/Idempotency/Source Health/Execution State 不得存在第二套可写真相；JSON/JSONL 仅用于 Export/Debug/Log/Snapshot/Metrics（SPAC §4 / CH1-1.1）。
**Actual:** 任务/scanrun 调度真相已唯一化到 SQLite（`persistence/sqlite.py`，`daemon.py:278-280`），task_registry.json/scan_runs.json 已死（生产零实例化）。但运行时仍有活跃 JSON 第二真相：`actions/approval/inbox.py:24` approvals.json、`actions/idempotency/store.py:36` idempotency.json、`actions/policy/killswitch.py:18` ks.json、`notifications/dedup.py:42-48` dedup JSON、`memory/observations/store.py` observations.json、`security/credential_vault/vault.py:39` credentials.json。`persistence/repos.py` 的 9 个 SQLite repo（Event/Outbox/Observation/Memory/Notification/Approval/Action/Audit/SourceHealth）全仓库零装配（仅测试实例化，如 test_p1_persistence.py:162）；`service.py:37-42` RepositorySet 只接 tasks/scan_runs/memory（注释自认"后续 Sprint 并入"）。
**Status:** FAIL
**Severity:** P0
**Affected Modules:** persistence/repos.py, service.py, actions/{approval,idempotency,policy}, notifications/dedup.py, memory/observations, security/credential_vault
**Missing Work:** 把 Approval/Idempotency/Notification/Observation/KillSwitch 状态迁移到 SQLite Repository 并全部接入 RepositorySet；事件/通知/审批/执行路径启用 SQLite 写入；JSON 仅保留 export/debug/log 用途；删除运行期 JSON 写路径。
**Recommended Chapter:** CHAPTER 1（1.1-1.7）

---

**Requirement:** FR-082
**Expected:** Hotel Live：完整 Pipeline Search→Detail→Room Normalize→Availability→Policy Normalize→Price→Verify→Score→Rank（SPAC §17 / CH4-4.4）。
**Actual:** 无任何真实 Hotel Live Source——booking 只是 replay fixture（`tests/replay/fixtures/booking.json`，`apps/agent_cli.py:68` 用 `load_fixtures(...,"booking")`）；`coordinator/scanner/hotel.py` 管线存在（normalize/policy/score/rank 走通），但 **Detail/Availability/Verify 三步无对应代码**（availability 恒默认 UNKNOWN）；hotel 实体解析无容错分级（`domains/hotel/knowledge.py:15-24` 仅精确匹配）。
**Status:** PARTIAL
**Severity:** P0
**Affected Modules:** adapters/（无 hotel 源）, coordinator/scanner/hotel.py, domains/hotel/{normalize,knowledge}.py, apps/agent_cli.py
**Missing Work:** 接入至少一个真实 Hotel Live Source（Booking/Agoda/携程酒店）；补 Detail/Availability/Verify 环节；hotel entity resolution 增加容错分级；Live Bundle 依赖此源（FR-090/091 只对真实数据成立）。
**Recommended Chapter:** CHAPTER 4（4.4/4.5/4.6）

---

### 3.2 P1（15 项）

---

**Requirement:** FR-021
**Expected:** 关键事件支持 SQLite EventStore + Transactional Outbox + Dispatcher + Retry + Dead Letter；进程崩溃不应静默丢失重要事件（SPAC §9 / CH1-1.2）。
**Actual:** 组件齐全且有测试：`persistence/repos.py:32-86`（Event/Outbox repo）、`events/reliable.py:29-99`（OutboxDispatcher + retry + DLQ）、`test_p2_reliable_events.py` 5 项全过（含 restart 与同事务写）。但**生产代码零 enqueue/零 dispatcher 运行**（grep 仅 `events/__init__.py` 导出与测试引用），事件只走进程内 `InProcessEventBus`（`events/bus.py`），崩溃即丢。
**Status:** PARTIAL
**Severity:** P1
**Affected Modules:** events/reliable.py, events/bus.py, persistence/repos.py, coordinator/scheduler/daemon.py, apps/scheduler.py
**Missing Work:** 扫描/通知/审批关键路径接入 outbox enqueue + 后台 Dispatcher（daemon 内 run_forever），业务状态与 outbox 同事务写。
**Recommended Chapter:** CHAPTER 1（1.2）

---

**Requirement:** FR-014
**Expected:** 多进程/多 Worker 环境下同一 Task 不得重复运行，使用 DB-backed RunLease（SPAC §7 / CH1-1.7）。
**Actual:** RunLease 实现完整（`coordinator/scheduler/runlease.py`：acquire/renew/release/recover_expired/is_owned，`run_leases` 表）且有测试（`test_p11_runlease.py`、`test_p11_service_lease.py`）。但**生产装配未接线**：`load_watch_daemon`（`daemon.py:266-294`）与 `apps/scheduler.py` 创建 WatchDaemon 时均未传 lease（daemon 的 lease 参数默认 None）——生产运行路径无租约保护。
**Status:** PARTIAL
**Severity:** P1
**Affected Modules:** coordinator/scheduler/{daemon.py,runlease.py}, apps/scheduler.py, service.py
**Missing Work:** load_watch_daemon 创建 RunLease(db) 并注入 WatchDaemon（baseline/retry/misfire 三路径已支持，只需传参）；补生产级集成测试。
**Recommended Chapter:** CHAPTER 1（1.7）

---

**Requirement:** FR-015
**Expected:** 进程崩溃后重启必须：恢复 Watch、恢复 Scheduler、识别未完成 ScanRun、安全重试、避免重复不可逆 Action（SPAC §7 / CH1-1.7）。
**Actual:** Watch/Scheduler 恢复有（SQLite + load_watch_daemon 启动落库）；**无 RUNNING ScanRun 识别/恢复逻辑**——`coordinator/checkpoint/checkpoint.py:39-49` 的 in_flight 只写不读（无启动时 reconcile）；retry 只处理 FAILED_RETRYABLE（`daemon.py:129-179`），RUNNING 残留无人接管；避免重复 Action 靠 idempotency reconcile（`actions/gateway/transaction.py:176-218`，有实现）。
**Status:** PARTIAL
**Severity:** P1
**Affected Modules:** coordinator/checkpoint/checkpoint.py, coordinator/scheduler/daemon.py, coordinator/task_registry/scanruns.py
**Missing Work:** daemon 启动时扫描 RUNNING 残留 ScanRun → 判定（已提交/可重试/需人工）→ 安全重试或标记；checkpoint.in_flight 启动时回收。
**Recommended Chapter:** CHAPTER 1（1.7）

---

**Requirement:** FR-164
**Expected:** 通知事件至少 PRICE_DROP/RARE_OPPORTUNITY/AVAILABILITY_CHANGE/WATCH_FAILED/APPROVAL_REQUIRED/ACTION_RESULT（SPAC §27）。
**Actual:** `events/types.py:7-56` 无上述任一事件类型；仅有通用 NOTIFICATION_REQUESTED/NOTIFICATION_SENT/OPPORTUNITY_DETECTED/APPROVAL_REQUESTED/ACTION_EXECUTED/ACTION_FAILED。6 个 token 全仓库代码 grep 零命中（唯一相近是动作状态 REAPPROVAL_REQUIRED，`actions/gateway/transaction.py:93`，属另一概念）。
**Status:** NOT_IMPLEMENTED
**Severity:** P1
**Affected Modules:** events/types.py, notifications/, coordinator/scanner/
**Missing Work:** 定义 6 种通知事件类型并在对应触发点发出（价格下跌/稀有机会/库存变化/Watch 失败/审批请求/动作结果）。
**Recommended Chapter:** CHAPTER 2（2.2）+ CHAPTER 5（5.6）

---

**Requirement:** FR-074
**Expected:** 目标架构支持 Skyscanner/Trip/Ctrip/Fliggy/Tongcheng/Other 多 Flight Source；不可访问时明确 DEGRADED/UNAVAILABLE（SPAC §16 / CH4-4.2/4.3）。
**Actual:** 真实 Flight Live 源**只有 Skyscanner 一个**（`adapters/skyscanner/adapter.py`，scrapling 浏览器渲染，manifest `skyscanner_marketplace_manifest` 注册于 `apps/shadow_scan.py:53` 与 `apps/scheduler.py:41`）；ctrip/fliggy 仅为 replay fixture（`tests/replay/fixtures/`，`adapters/replay/adapter.py` 从磁盘加载）；Trip/Tongcheng/Other 零代码；`apps/agent_cli.py:31-37` 注册的 ctrip/fliggy "市场" 无对应 live fetcher。DEGRADED 机制真实（`adapters/health/tracker.py` + scanner 逐源 try/except）。
**Status:** PARTIAL
**Severity:** P1
**Affected Modules:** adapters/{skyscanner,replay}, coordinator/source_planner/planner.py, apps/{agent_cli,scheduler,shadow_scan}.py
**Missing Work:** 接入第二/第三真实 Flight Source（Ctrip/Trip 官方 API 或浏览器适配器）；SourcePlanner 按 Health/Capability/Cost 选择（已有 `plan_sources`，缺真实多源可计划）。
**Recommended Chapter:** CHAPTER 4（4.2/4.3）

---

**Requirement:** FR-172 / FR-173
**Expected:** L2 可自动推进到 confirmation page 之前；L3/L4 必须同时满足 Policy Allow + Approval + Valid Quote Snapshot + Slippage Check + Idempotency + Executor（SPAC §28 / CH8-8.5/8.6）。
**Actual:** 主网关硬禁：`actions/gateway/gateway.py:25-28` `OPEN_LEVELS={L0_SCAN,L1_RECOMMEND}`、`BLOCKED_LEVELS={L2_PREPARE,L3_CONFIRM,L4_EXECUTE}`，`check_intent`（`:38-41`）对 L2+ 直接抛 CapabilityDenied("blocked in V1")。L3/L4 全套机制已在 `actions/gateway/transaction.py` 实现且单测齐全（Policy/Slippage/Snapshot/Idempotency/Approval/Executor/Reconcile；`test_phase7_execution.py`、`test_p16_controlled.py`、`test_p09_approval.py`、`test_p0_transaction.py`），但只能绕过主网关直接 new TransactionExecutor/ControlledExecutor 才可达（测试/CLI 即如此）。Skill 层 prepare_action 返回 NOT_READY（`adapters/skyscanner/adapter.py:190-193`）；`ActionPreparer`（`prepare.py:41-43`）自述"here it's the plan only"。
**Status:** NOT_IMPLEMENTED（FR-172）/ PARTIAL（FR-173）
**Severity:** P1
**Affected Modules:** actions/gateway/{gateway,prepare,execute,transaction}.py, adapters/skyscanner/adapter.py
**Missing Work:** ① L2：实现 skill 级 prepare_action（导航到确认页，不 commit）+ 打开网关 L2 通道；② L3/L4：按 CH8 门禁逐步放开 BLOCKED_LEVELS，接入真实 executor（预订/支付平台），端到端走通 Policy+Approval+Snapshot+Slippage+Idempotency+Audit。
**Recommended Chapter:** CHAPTER 8（8.4/8.5/8.6）

---

**Requirement:** FR-191 / FR-192
**Expected:** Production 支持 macOS Keychain / Windows Credential Manager（SPAC §30 / CH8-8.1）。
**Actual:** 全仓库无 macOS Security Framework/Keychain 与 Windows Credential Manager/wincred 任何代码（grep 零命中）。`security/credential_vault/vault.py` 是 base64+XOR 轻量混淆 + **硬编码固定 dev key `_KEY = b"ua-dev-vault-2026"`**（`:20`），docstring 自认"开发/影子模式…生产环境应接 OS Keychain"。FR-190 本身达标（明文不落盘、masked 视图、测试 `test_p14_security.py`），但生产后端缺失。
**Status:** NOT_IMPLEMENTED
**Severity:** P1
**Affected Modules:** security/credential_vault/vault.py
**Missing Work:** 实现 KeychainBackend（macOS）与 CredentialManagerBackend（Windows），CredentialVault 抽象化后端选择，移除固定 XOR key，dev 混淆降级为兜底。
**Recommended Chapter:** CHAPTER 8（8.1）

---

**Requirement:** FR-193 / FR-194
**Expected:** Identity Vault 独立于普通 Memory；Session Broker 独立管理外部平台 Session（SPAC §30 / CH8-8.2/8.3）。
**Actual:** `security/identity_vault/__init__.py` 与 `security/session_broker/__init__.py` 均为 **0 字节**（实测 wc -l = 0），无任何实现。
**Status:** NOT_IMPLEMENTED
**Severity:** P1
**Affected Modules:** security/identity_vault/, security/session_broker/
**Missing Work:** 实现 IdentityVault（身份数据独立存储，与 Memory 隔离，含 FR-104 human-only 身份声明支持）与 SessionBroker（外部平台 Session 生命周期/刷新/吊销管理）。
**Recommended Chapter:** CHAPTER 8（8.2/8.3）

---

**Requirement:** FR-132
**Expected:** Decision 必须引用 supporting_evidence[]（SPAC §23 / RULE-006）。
**Actual:** `core/decision/` 空目录（0 字节）；全仓库 grep `supporting_evidence` 零命中；无任何 Decision 契约类——"决策"仅表现为 OpportunityScore（`core/opportunity/engine.py`，无 evidence 列表）与 TriggerEvent，均无 supporting_evidence 字段。Decision Memory 只有 kind 字符串（`memory/domains.py:50-56`）。
**Status:** NOT_IMPLEMENTED
**Severity:** P1
**Affected Modules:** core/decision/, core/contracts/, core/opportunity/engine.py, memory/domains.py
**Missing Work:** 定义 Decision 契约（decision_id/task_id/supporting_evidence[]/score/reason/trace_id），在机会命中处生成并持久化到 SQLite decisions 表；Decision 引用 Evidence 列表。
**Recommended Chapter:** CHAPTER 4（4.6）+ CHAPTER 5（5.4）

---

**Requirement:** FR-092
**Expected:** 每个推荐 Bundle 必须返回 why_this_bundle（SPAC §18 / CH4-4.7）。
**Actual:** 全仓库 grep `why_this_bundle` 0 命中。`core/contracts/bundle.py:11-24` BundleCandidate 只有 `notes: list[str]`（组合过程备注，非每个推荐的结构化解释）；`core/bundling/optimizer.py:97-105` 仅在"非最便宜机票胜出"时追加一条说明。
**Status:** NOT_IMPLEMENTED
**Severity:** P1
**Affected Modules:** core/contracts/bundle.py, core/bundling/optimizer.py, domains/travel/bundle.py
**Missing Work:** BundleCandidate 增加 why_this_bundle 字段（组件价格/时长/转机/到达时间/酒店位置/退改/偏好/验证置信度的结构化原因），optimizer 为每个推荐生成。
**Recommended Chapter:** CHAPTER 4（4.7）

---

**Requirement:** FR-052
**Expected:** Skill Verify 确认 Price/Availability/Conditions/Freshness（SPAC §12 / CH4-4.6）。
**Actual:** Skyscanner verify 是 fail-closed stub：恒返回 `{"verified": False, "status": "UNVERIFIED"}`（`adapters/skyscanner/adapter.py:183-185`）；官方验证源 `adapters/official/registry.py:57-65` NoOpOfficialVerifier 恒返回 None、StubOfficialVerifier 仅供测试。确定性 FlightVerifier（`core/verification/verifier.py`）存在（多报价聚合+置信度+Evidence），但依赖多报价，单源下无真实验证路径。
**Status:** NOT_IMPLEMENTED
**Severity:** P1
**Affected Modules:** adapters/skyscanner/adapter.py, adapters/official/registry.py, core/verification/verifier.py
**Missing Work:** 实现至少一个 Tier2/Tier3 真实验证源（OTA 详情页/航司官网价格核对），skill verify 返回真实 verified 结果。
**Recommended Chapter:** CHAPTER 4（4.6）

---

**Requirement:** FR-060 / FR-061 / FR-062 / FR-063
**Expected:** 正式建立通用 HTTP / API / Browser Adapter；Mobile 第一阶段可仅定义 Protocol（SPAC §13 / CH3-3.1~3.4）。
**Actual:** `adapters/http/`、`adapters/api/`、`adapters/browser/`、`adapters/mobile/` 四目录**全部只有 0 字节 `__init__.py`**（实测 wc -c = 0），无任何协议或实现；唯一痕迹是 `SkillManifest.transport` 字符串枚举（`core/contracts/registry.py:18`：api|http|browser|mobile）。Skyscanner 用 scrapling 直连浏览器（`adapters/skyscanner/adapter.py:201-259`），未走 browser adapter 抽象。**FR-063 连第一阶段 Protocol 契约都没有。**
**Status:** NOT_IMPLEMENTED
**Severity:** P1
**Affected Modules:** adapters/{http,api,browser,mobile}/
**Missing Work:** 定义各 Adapter 协议（BaseAdapter + HTTP/API/Browser/Mobile 子协议），实现 HTTP（通用抓取）、API（认证+速率限制）、Browser（playwright/scrapling 封装）；Mobile 至少定义 Protocol 契约（SPAC 允许第一阶段仅 Protocol）。
**Recommended Chapter:** CHAPTER 3（3.1-3.4）

---

**Requirement:** FR-180（缺口补充）
**Expected:** Kill Switch 开启后禁止所有受控写操作（SPAC §29 / CH8-8.9）。
**Actual:** KillSwitch 实现完整（`actions/policy/killswitch.py:17-71`：kill/disarm/is_killed/assert_alive + JSON 持久化）并在 TransactionExecutor（`transaction.py:63-67`）与 ControlledExecutor（`execute.py:58-62`）入口强制，测试覆盖（`test_p16_controlled.py:57-64`、`test_phase7_execution.py:102-122`）。但 **L0/L1 的 `ActionGateway.execute`（`gateway.py:54-68`）与 `ActionPreparer`（`prepare.py`）不检查 KillSwitch**——L2 prepare 路径可绕过急停。
**Status:** PARTIAL
**Severity:** P1
**Affected Modules:** actions/gateway/{gateway,prepare}.py, actions/policy/killswitch.py
**Missing Work:** ActionGateway.check_intent 与 ActionPreparer 入口调用 killswitch.assert_alive()；补测试。
**Recommended Chapter:** CHAPTER 8（8.9）

---

**Requirement:** FR-140 / FR-141 / FR-142
**Expected:** OpportunityScore 综合 Current Price/Historical Baseline/Percentile/Availability/Verification/Confidence/Preference/Time Remaining/Source Health；Result 返回 OpportunityScore/Confidence/Reason/Evidence/RecommendedAction；识别 明显低于历史+库存稀缺+时间窗口临近+用户高度偏好 的稀有机会（SPAC §25 / CH5-5.1~5.5）。
**Actual:** `core/opportunity/engine.py:36-83` 实现 price/historical low/percentile/availability/verification/confidence 分量（确定性加权，含 fail-closed）。但：**无 Time Remaining 分量**（全仓库无 deadline 概念，`coordinator/deadline/` 0 字节空目录）、**无 User Preference 分量**（PreferenceLearner 存在但未被任何管线消费）、**无 Source Health 分量**；OpportunityScore（`core/contracts/scoring.py:26`）无 Reason/Evidence/RecommendedAction 字段；稀有机会（FR-142）仅 historical_low + availability LOW 两信号，无组合检测器。
**Status:** PARTIAL
**Severity:** P1
**Affected Modules:** core/opportunity/engine.py, core/contracts/scoring.py, coordinator/deadline/, memory/preferences/learner.py
**Missing Work:** OpportunityScore 增加 time_remaining/preference/source_health 分量；Result 增加 reason/evidence/recommended_action；实现稀有机会组合检测器。
**Recommended Chapter:** CHAPTER 5（5.1-5.5）

---

**Requirement:** FR-130
**Expected:** 每次 Source Scanner 得到真实 Observation（SPAC §23 / CH1-1.3）。
**Actual:** Flight 扫描会记录 Observation（`coordinator/scanner/shadow.py:168-171` 写 ObservationStore.record）；但 **Hotel/Job 扫描的 observations 参数从未使用**（`coordinator/scanner/hotel.py:25-27`、`job.py:27-29` 可注入但无写路径）；且 ObservationStore 是 JSON 持久化（`memory/observations/store.py`，RULE-003 违规）。
**Status:** PARTIAL
**Severity:** P1
**Affected Modules:** coordinator/scanner/{shadow,hotel,job}.py, memory/observations/store.py
**Missing Work:** Hotel/Job 扫描同样记录 Observation；Observation 迁移 SQLite（并入 RULE-003 工作）。
**Recommended Chapter:** CHAPTER 1（1.3）+ CHAPTER 4/6

---

### 3.3 P2（13 项）

---

**Requirement:** FR-001
**Expected:** OneShot：立即运行一次扫描（SPAC §5）。
**Actual:** TaskType.ONESHOT 枚举存在（`core/contracts/task.py:18`），但全仓库无 task.type 分发——scanner/daemon 不区分任务类型（同一路径执行）；"立即运行一次"只能通过 `agent_cli.py --domain` 或 DSH 插件工具在协议外实现（且与 FR-030 未实现相关）。
**Status:** PARTIAL
**Severity:** P2
**Affected Modules:** core/contracts/task.py, coordinator/, apps/agent_cli.py
**Missing Work:** run_task_once 落地后（FR-030），OneShot 任务类型经协调器一次执行并归档。
**Recommended Chapter:** CHAPTER 2（2.1）

---

**Requirement:** FR-005
**Expected:** Composite：支持多个条件组合（如 价格<¥4000 AND 总时间<25h AND 最多一次转机）（SPAC §5）。
**Actual:** `core/constraints/` 空目录（0 字节）；TriggerRule（`core/contracts/task.py:104-107`）仅支持 opportunity_score_gte/price_drop_cny_gte/price_drop_percent_gte/historical_low 四阈值；`scanner/shadow.py:_maybe_notify`（`:272-305`）与 `trigger_engine/engine.py:21-33` 均为 **OR 语义**（任一条件命中即触发），无 AND 组合；无时长/转机/机场等候选属性条件。转机/时长约束只存在于 flight scoring 配置（`domains/flight/scoring.py:33-35` max_stops/max_layover/max_total_hours），非触发条件。
**Status:** PARTIAL
**Severity:** P2
**Affected Modules:** core/constraints/, core/contracts/task.py, coordinator/trigger_engine/engine.py, coordinator/scanner/shadow.py
**Missing Work:** 实现通用 Constraint 求值（候选属性谓词 + AND 组合），接入扫描管线与触发判定。
**Recommended Chapter:** CHAPTER 1 + CHAPTER 5（5.5）

---

**Requirement:** FR-006
**Expected:** MultiDomain：一个 Task 可同时涉及多个 Domain（Flight+Hotel+Travel Bundle）（SPAC §5）。
**Actual:** `TaskSpec.domain` 是单值 `TaskDomain`（`core/contracts/task.py:117`）；跨域只到候选层 bundle 组合（`domains/travel/bundle.py:24-76`），一个 WatchTask 不能声明多 Domain 扫描。
**Status:** PARTIAL
**Severity:** P2
**Affected Modules:** core/contracts/task.py, coordinator/, domains/travel/bundle.py
**Missing Work:** TaskSpec 支持 domains[] 多值或子任务拆分，协调器按域并行扫描后聚合。
**Recommended Chapter:** CHAPTER 4（4.7）+ CHAPTER 1

---

**Requirement:** FR-051 / FR-053
**Expected:** Skill Detail 返回结构化详情；Skill Availability 查询实时可用状态（SPAC §12）。
**Actual:** Skyscanner detail 恒返回 `{"detail": {}, "status": "NOT_AVAILABLE"}`（`adapters/skyscanner/adapter.py:179-181`）；availability 恒返回 `{"available": None, "status": "UNKNOWN"}`（`:187-188`）；manifest 声明 `detail: False, availability: False`（`adapters/skyscanner/manifest.py:18-19`）。测试仅验证"不崩"（`test_p8_skill_protocol.py:42-45, 55-57`）。
**Status:** NOT_IMPLEMENTED
**Severity:** P2
**Affected Modules:** adapters/skyscanner/adapter.py, adapters/skyscanner/manifest.py
**Missing Work:** 实现详情页解析（航班/酒店详情结构化）与库存可订状态查询；或为其他已接源提供该能力。
**Recommended Chapter:** CHAPTER 4（4.4/4.5）

---

**Requirement:** FR-054
**Expected:** Skill Prepare Action：允许推进到提交/支付确认之前，但不得 Commit（SPAC §12）。
**Actual:** Skill 层 prepare_action 是 stub：恒返回 `{"status": "NOT_READY", "reason": "prepare_action not implemented (P8 search-only)"}`（`adapters/skyscanner/adapter.py:190-193`）；Action 层 `ActionPreparer`（`actions/gateway/prepare.py:38-128`）真实实现"计划+审批申请+幂等+audit"（测试 `test_p15_prepare.py`），但 L2 被网关硬禁（FR-172），无法端到端推进到确认页。
**Status:** PARTIAL
**Severity:** P2
**Affected Modules:** adapters/skyscanner/adapter.py, actions/gateway/prepare.py
**Missing Work:** 依赖 FR-172 放开 L2 后，skill 实现真实 prepare（导航到确认页/预填表单，不提交）。
**Recommended Chapter:** CHAPTER 8（8.4）+ CHAPTER 4

---

**Requirement:** FR-055
**Expected:** Health Check 统一状态 HEALTHY/DEGRADED/UNAVAILABLE/RATE_LIMITED/AUTH_REQUIRED（SPAC §12 / CH3-3.6）。
**Actual:** 状态**无正式 Enum**——只是字符串常量+注释（`core/contracts/registry.py:22,36`、`registry/skills/resolver.py:15-16` 排序表 `_HEALTH_ORDER` 含 5 状态）；`adapters/health/tracker.py:66-71` 状态机只产生 HEALTHY/DEGRADED/UNAVAILABLE，RATE_LIMITED/AUTH_REQUIRED 无生产路径；SkyscannerAdapter.health_check 硬编码 `{"status": "UNKNOWN"}`（`adapter.py:195-198`）。
**Status:** PARTIAL
**Severity:** P2
**Affected Modules:** registry/skills/resolver.py, adapters/health/tracker.py, adapters/skyscanner/adapter.py, core/contracts/registry.py
**Missing Work:** 定义 HealthStatus 枚举；health_check 返回真实延迟/最近成功时间；接入 RATE_LIMITED/AUTH_REQUIRED 检测。
**Recommended Chapter:** CHAPTER 3（3.6）

---

**Requirement:** FR-072
**Expected:** Flight Scoring 至少考虑 Price/Duration/Stops/Airport/Schedule/Confidence/Verification/User Preference（SPAC §16）。
**Actual:** `domains/flight/scoring.py:153-170` 实现 price/stops/layover/total_time/quality 五维加权（fail-closed：stops=-1 不给直飞分）；**缺 Airport、Schedule、Confidence、Verification、User Preference** 维度（PreferenceLearner 未接入评分）。
**Status:** PARTIAL
**Severity:** P2
**Affected Modules:** domains/flight/scoring.py, core/scoring/, memory/preferences/learner.py
**Missing Work:** 评分增加 confidence/verification 系数与用户偏好权重；Airport/Schedule 维度。
**Recommended Chapter:** CHAPTER 4（4.1）+ CHAPTER 5（5.4）

---

**Requirement:** FR-081
**Expected:** 不同平台上的同一家酒店必须尽可能正确合并（SPAC §17 / CH4-4.5）。
**Actual:** `domains/hotel/knowledge.py:15-24` 实体键仅按名称/位置精确匹配合并，**无容错分级**（对比 Flight 的 strong/weak key + PROBABLE_MATCH 保护，`domains/flight/knowledge.py:44-106`，字段缺失时不强合并）；单源（仅 booking fixture）下实际未发生跨平台合并。
**Status:** PARTIAL
**Severity:** P2
**Affected Modules:** domains/hotel/knowledge.py
**Missing Work:** 酒店实体解析增加强/弱键分级与字段缺失保护，避免错误合并。
**Recommended Chapter:** CHAPTER 4（4.5）

---

**Requirement:** FR-091
**Expected:** Total Trip Utility 不得简单 Cheapest Flight + Cheapest Hotel；考虑 Travel Time/Stops/Arrival/Check-in Compatibility/Airport/Location/Cancellation/Preferences/Verification Confidence（SPAC §18）。
**Actual:** `core/bundling/optimizer.py:30-108` 实现总效用（约束下非贪心，`test_p10_bundle.py` 证明非最便宜机票组合可胜出）；但维度仅 cost_score+quality 加权，**无 Arrival Time/Check-in Compatibility/Airport/Location/Cancellation/Preferences/Verification Confidence** 显式维度。
**Status:** PARTIAL
**Severity:** P2
**Affected Modules:** core/bundling/optimizer.py, core/contracts/bundle.py, domains/travel/bundle.py
**Missing Work:** 扩展 BundleComponent/BundleCandidate 携带上述维度并纳入效用计算。
**Recommended Chapter:** CHAPTER 4（4.7）

---

**Requirement:** FR-101
**Expected:** Job Matching 根据 用户背景/技能/地点/职位类型/公司/签证/工作权/偏好 产生匹配结果（SPAC §19）。
**Actual:** `domains/jobs/` 实现技能匹配 match_ratio（`knowledge.py:34-40`）、薪资（`:43-47`）、评分 match/salary/trust（`scoring.py:13-34`）、entity_key 含 company/title/location/job_reference（`knowledge.py:14-23`）；**缺签证/工作权维度与用户偏好接入**。
**Status:** PARTIAL
**Severity:** P2
**Affected Modules:** domains/jobs/{knowledge,scoring,normalize}.py
**Missing Work:** 增加 visa/work-right 匹配维度；偏好学习接入 job 匹配。
**Recommended Chapter:** CHAPTER 6（6.2）

---

**Requirement:** FR-102
**Expected:** Application State：DISCOVERED/SHORTLISTED/PREPARED/NEEDS_USER/READY/SUBMITTED/FAILED（SPAC §19 / CH6-6.3）。
**Actual:** 全仓库无 ApplicationState 状态机（grep 各状态名零命中）；DISCOVERED 只是 DataCompleteness（`core/contracts/raw.py:124`），PREPARED 只是 prepare/idempotency 的字符串状态（`actions/gateway/prepare.py:28,124`）。
**Status:** NOT_IMPLEMENTED
**Severity:** P2
**Affected Modules:** domains/jobs/, core/contracts/
**Missing Work:** 定义 ApplicationState 状态机与持久化，接入 job 申请流程。
**Recommended Chapter:** CHAPTER 6（6.3）

---

**Requirement:** FR-103
**Expected:** 用户确认过的历史回答可以复用（SPAC §19 / CH6-6.4）。
**Actual:** `domains/jobs/action.py:52-59` store_answer_memory 可存 TASK 域 answer，`memory/store.py:62-68` 可读，测试证明可复用（`test_p13_careerpilot.py:23-33`）；但**无任何产品流程消费已存答案**（全库仅定义处与测试引用 `answer::`），"自动复用"未接线。
**Status:** PARTIAL
**Severity:** P2
**Affected Modules:** domains/jobs/action.py, memory/
**Missing Work:** 在申请填写流程中查询已存 answer 并预填/提示复用。
**Recommended Chapter:** CHAPTER 6（6.4）

---

**Requirement:** FR-104
**Expected:** Personality Test/Psychological Assessment/Identity Declaration/Truthfulness Declaration 默认 Human-only，禁止第三方代答（SPAC §19 / CH6-6.5）。
**Actual:** `domains/jobs/action.py:69-89` is_human_only + `_HUMAN_ONLY_MARKERS` 覆盖性格/MBTI/人格/价值观测试/身份证/护照/出生日期/社保/法律敏感等关键词，测试通过（`test_p13_careerpilot.py:36-42`）；但该函数**未接入任何回答生成/执行流**（无调用点），"禁止 AI 代答"无强制点。
**Status:** PARTIAL
**Severity:** P2
**Affected Modules:** domains/jobs/action.py
**Missing Work:** 在回答生成/申请提交管线强制调用 is_human_only（命中即转人工，阻断自动代答）。
**Recommended Chapter:** CHAPTER 6（6.5）

---

**Requirement:** FR-113 / FR-114 / FR-115 / FR-116 / FR-117
**Expected:** Railway 至少实现 Scoring/Live Skill/Availability/Watch/Verification，满足后才标记 RAILWAY_LIVE_READY（SPAC §20 / CH7）。Ecommerce/Food 同样需 Raw/Normalize/Entity/Price/Availability/Source/Verify/Score/Watch/Prepare 与 ECOMMERCE_LIVE_READY/FOOD_LIVE_READY。
**Actual:** `domains/railway/` 只有 normalize.py（52 行）+ `__init__.py`；FR-110 Raw Contract（`core/contracts/raw.py:185-200` RawRailway）、FR-111 Normalize、FR-112 Entity Key 已实现且有测试（`test_p17_19_domains.py:16-31`）；**无 scoring、无 live skill、无 availability、无 watch、无 verification**；全仓库 grep `RAILWAY_LIVE_READY`/`ECOMMERCE_LIVE_READY`/`FOOD_LIVE_READY` 零命中。Ecommerce（`domains/ecommerce/normalize.py` 48 行）/Food（`domains/food/normalize.py` 44 行）同构：仅 normalize + entity_key。
**Status:** NOT_IMPLEMENTED
**Severity:** P2
**Affected Modules:** domains/railway/, domains/ecommerce/, domains/food/, adapters/
**Missing Work:** 按 CH7 顺序补齐每域 Scoring/Skill/Source/Verify/Watch/Notification，并声明 *_LIVE_READY。
**Recommended Chapter:** CHAPTER 7

---

**Requirement:** FR-133
**Expected:** 支持 Decision→Evidence→Observation→Source 反查（SPAC §23）。
**Actual:** trace_id 贯穿事件链（`events/envelope.py:21-25`），Observation 有 evidence_refs（`contracts/observation.py:29`），Evidence 有 source（`contracts/observation.py:37-44`）；但 **无 Decision 层**（FR-132）且无任何反查 API/查询函数——链的起点不存在。
**Status:** PARTIAL
**Severity:** P2
**Affected Modules:** core/decision/, core/contracts/, observability/
**Missing Work:** 依赖 FR-132 建立 Decision 后，实现按 decision_id/trace_id 反查 Evidence/Observation/Source 的查询接口。
**Recommended Chapter:** CHAPTER 4（4.6）+ CHAPTER 5

---

**Requirement:** FR-160
**Expected:** 通知去重持久化，重启后仍知道通知是否已发送（SPAC §27 / CH5-5.6）。
**Actual:** `notifications/dedup.py:30-48,70-76` 支持 JSON 持久化+重启恢复，重启测试通过（`test_p0_hardening.py:17-37`）；但**生产装配从不传 state_path**——`agent_cli.py:52-55` 与 `apps/scheduler.py:48-51` 均用默认 `NotificationDedup()`（内存态），实际运行时重启即忘；`WatchTask.notified_fingerprints`（`task.py:139`）声明未用。
**Status:** PARTIAL
**Severity:** P2
**Affected Modules:** notifications/dedup.py, apps/{agent_cli,scheduler}.py, core/contracts/task.py
**Missing Work:** 生产装配传入持久化 state_path（或迁移 SQLite，见 RULE-003）；用 notified_fingerprints 或 SQLite 做重启安全去重。
**Recommended Chapter:** CHAPTER 5（5.6）

---

**Requirement:** FR-162 / FR-163
**Expected:** 通知优先级至少 LOW/NORMAL/HIGH/URGENT；支持抽象通道 Harness/Desktop/Mobile/Webhook/Jarvis/Future（SPAC §27）。
**Actual:** 全仓库无 Priority 枚举/字段（grep URGENT 0 命中；TaskSpec 无 priority 字段）；无 Channel 抽象——`hosts/protocol/notification.py:8-17` 仅 NotificationProvider/ApprovalProvider 两个 ABC，"channel decided by host" 只是 docstring（`:11`），无任何通道类/枚举。
**Status:** NOT_IMPLEMENTED
**Severity:** P2
**Affected Modules:** notifications/, hosts/protocol/notification.py, core/contracts/task.py
**Missing Work:** 定义 NotificationPriority 枚举与 Channel 抽象（Harness/Desktop/Mobile/Webhook/Jarvis），通知带 priority+channel 路由。
**Recommended Chapter:** CHAPTER 2（2.2）+ CHAPTER 5（5.6）

---

### 3.4 P3（4 项）

---

**Requirement:** FR-150
**Expected:** Memory Scope 支持 GLOBAL/USER/DOMAIN/TASK（SPAC §26）。
**Actual:** `core/contracts/base.py:25-31` Scope = GLOBAL/DOMAIN/TASK/SESSION——**无 USER scope**；用户隔离靠 MemoryRecord.user_id 字段（`contracts/memory.py:31`），语义不完全等价。
**Status:** PARTIAL
**Severity:** P3
**Affected Modules:** core/contracts/base.py, memory/sqlite_store.py
**Missing Work:** 明确 USER scope 语义（或文档化 user_id=USER scope 的映射）。
**Recommended Chapter:** CHAPTER 5（5.4）

---

**Requirement:** FR-154 / FR-155
**Expected:** 自动学习出的 Preference 必须保留来源；Preference 更新必须可撤销或恢复旧版本（SPAC §26）。
**Actual:** `memory/preferences/learner.py`：evidence 字段存在但极简（`_update_platform_preference` 写 `evidence: "observed ... acceptances"`）；`rollback()`（`:72-83`）并非真版本回滚——只是重写一个低置信度（0.3）的新值并打 `rolled_back` 标记，无版本历史存储（MemoryRecord 有 version 字段但只递增不保留历史）。测试 `test_p12_preference.py:47-74` 验证"可写回"而非"恢复旧版本"。
**Status:** PARTIAL
**Severity:** P3
**Affected Modules:** memory/preferences/learner.py, memory/sqlite_store.py
**Missing Work:** 偏好版本历史表（或 SQLite 快照），rollback 恢复上一版本而非覆盖。
**Recommended Chapter:** CHAPTER 5（5.4）

---

**Requirement:** FR-055 相关 / RULE-003 列表项：Source Health 持久化
**Expected:** Source Health 是 SQLite 唯一真相（SPAC RULE-003 明确列出）。
**Actual:** `SqliteSourceHealthRepository`（`persistence/repos.py:255-271`）存在但零装配；`SkillRegistry.set_marketplace_health`（`registry/registry.py:60-62`）只改内存 dict，重启即失；`adapters/health/tracker.py` 独立 JSON/内存状态。三个健康状态源互不同步。
**Status:** PARTIAL
**Severity:** P3
**Affected Modules:** registry/registry.py, adapters/health/tracker.py, persistence/repos.py
**Missing Work:** Source Health 统一到 SQLite repository 并接入 registry。
**Recommended Chapter:** CHAPTER 3（3.6）+ CHAPTER 1（1.6）

---

**Requirement:** RULE-004 缺口
**Expected:** 所有 WatchTask 状态修改必须经 TaskCoordinator→StateMachine→TaskRepository（SPAC RULE-004）。
**Actual:** Host 侧合规；但 `WatchDaemon._advance` 直接 `registry.update`（`daemon.py:260`）与 `_mark_watch_failed` 直接置 FAILED 绕过 transition()（`daemon.py:247`），`coordinator/watch_manager/manager.py:39-83` 有 7 处直接 update（仅测试用）。Core 调度器自身绕过状态机校验。
**Status:** PARTIAL
**Severity:** P3
**Affected Modules:** coordinator/scheduler/daemon.py, coordinator/watch_manager/manager.py
**Missing Work:** daemon 状态推进（advance/mark_failed）改为经 StateMachine 合法转移（如新增 SHEDULED→FAILED 转移或经 Coordinator 命令）。
**Recommended Chapter:** CHAPTER 1（1.7）

---

**Requirement:** FR-142 时间窗口补充
**Expected:** Opportunity 考虑 Time Remaining（SPAC §25 / CH5-5.7）。
**Actual:** `coordinator/deadline/` 为 0 字节空目录；全仓库无 deadline/剩余时间概念进入机会评分；RuleAdaptiveScheduler 用 `task.meta["target_depart"]` 做扫描频率（`rule_adaptive.py`），与机会评分不连通。
**Status:** NOT_IMPLEMENTED
**Severity:** P3
**Affected Modules:** coordinator/deadline/, core/opportunity/engine.py
**Missing Work:** deadline 计算模块（expires_at/target_depart → 剩余天数）接入 OpportunityInput。
**Recommended Chapter:** CHAPTER 5（5.7）

---

## 4. PASS 清单（实现 + 测试覆盖，回归基线，共 35 项）

FR-002 Scheduled、FR-003 Watch、FR-004 ConditionWatch（`scanner/shadow.py:_maybe_notify` 内联接线）、FR-010 Persistent Scheduler、FR-011 Timezone（IANA+DST）、FR-012 Misfire（SKIP/RUN_ONCE/CATCH_UP_LIMITED）、FR-013 Retry（FAILED_RETRYABLE+backoff，Watch 保持 WATCHING）、FR-020 EventEnvelope、FR-034 Harness Restart、FR-040 Jarvis Host Swap、FR-041 Jarvis Capabilities、FR-050 Skill Search、FR-056 Execute Separation（无 execute_action）、FR-064 Failure Isolation、FR-070 Flight Normalize、FR-071 Flight Entity Resolution（strong/weak key）、FR-073 Ranking Eligibility（PARTIAL 仅 preliminary）、FR-080 Hotel Normalize（含 policy 归一化）、FR-083 Independent Failure、FR-090 BundleCandidate、FR-100 Job Normalize、FR-110/111/112 Railway Raw/Normalize/EntityKey、FR-131 Evidence（deterministic verifier）、FR-151 Confidence、FR-152 Preference Learning、FR-153 Policy Isolation、FR-161 Cooldown、FR-170 L0、FR-171 L1、FR-174 Snapshot（REAPPROVAL_REQUIRED）、FR-175 Idempotency（reserve/commit/finalize/reconcile）、FR-176 Reconciliation（CONFIRMED/NOT_FOUND/UNKNOWN 三分支）、FR-190 Credential Isolation（有 caveat：混淆非加密，FR-191/192 未实现）。

---

## 5. 下一步建议（按 Severity 收敛顺序）

1. **P0 关闭**：FR-030 run_task_once → FR-032 审批真实入口 → FR-031 通知真实送达（+FR-164 事件类型）→ FR-033 DSH 桥可移植 → RULE-003 JSON 双写清零（CH1 全量接线）→ FR-082 Hotel Live 源。主战场 = CHAPTER 2 + CHAPTER 1。
2. **P1**：FR-074 第二/第三 Flight 源 → FR-172/173 L2-L4 通道放开 → FR-191/192/193/194 生产安全后端 → FR-132/092 Decision/Explainability → FR-021/014/015 运行时接线 → FR-060~063 通用 Adapter。
3. **P2/P3**：CH6 Jobs 产品化（Application State/Live 源）、CH7 新 Domain 补齐、通知优先级/通道、机会评分补维度、deadline 接入。

---

*本报告由架构审计生成，依据代码证据（文件:行号均可复核）；不修改任何代码。END OF MISSING_FEATURE_REPORT*
