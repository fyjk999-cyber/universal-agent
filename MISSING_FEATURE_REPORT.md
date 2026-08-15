# MISSING_FEATURE_REPORT — SPAC vs ACTUAL CODE

> 依据 SPAC §49 生成 · 更新：2026-08-15（CHAPTER 0 Repository Reality Lock）
> 对比基准：仓库根 `SPAC.md`（Source of Truth）vs `universal-agent/universal_agent/` 实际代码 + `tests/`（514 tests 全绿）
> 证据原则：所有条目均以实际代码路径/行为为准，不信任文档声明。

## 总体结论

| 维度 | 结果 |
|---|---|
| FR 条目总数 | 89 个 FR 行（FR-001 ~ FR-194，部分 FR 为组式编号） |
| RULE 合规 | 10/10 合规（见下表） |
| 判定为 **PASS** 的 FR 组 | 约 21 组（任务类型/调度/事件/Skill/Host 独立性/Jarvis/Decision/Opportunity/Memory/Actions/KillSwitch 等） |
| 判定为 **PARTIAL** 的 FR | 约 14 组（Harness 集成、通用 Adapter、Flight 多源、Hotel Live、Jobs Live、Railway/Ecommerce/Food、Security 生产后端、Notification 分级等） |
| **NOT_IMPLEMENTED / FAIL** 的 FR | 5 项硬性 FAIL：FR-030、FR-031、FR-032、FR-033（CHAPTER 2）；FR-191/192 未实现（生产凭据后端）；FR-060/061/062/063 Adapter 空占位 |
| 未披露 P0 | **0**（所有缺口均已在本报告 + ROADMAP + KNOWN_LIMITATIONS 披露） |
| 未披露 P1 | **0**（P1 缺口 9 项全部披露，见下） |

### Chapter 完成度（与 ROADMAP 一致，代码证据）

| Chapter | 完成度 | 关键缺口 |
|---|---|---|
| CH 0 Repository Reality Lock | **COMPLETE**（本次达成） | — |
| CH 1 Runtime Composition | COMPLETE | — |
| CH 2 Harness Production Integration | **PARTIAL** | FR-030/031/032/033（P1） |
| CH 3 Generic Source Runtime | **PARTIAL** | FR-060/061/062/063 空占位 |
| CH 4 Travel Multi-Source | **PARTIAL** | FR-074 第二/三源、FR-082 Hotel Live、FR-071 跨源实体解析 |
| CH 5 Persistent Opportunity Watch | COMPLETE | — |
| CH 6 Jobs Productization | **PARTIAL** | FR-100/101 Live 源、FR-102 Application State |
| CH 7 Additional Domains | **PARTIAL** | FR-110~117 等仅骨架 |
| CH 8 Controlled Execution Productionization | **PARTIAL** | FR-191/192 生产凭据、FR-193/194 Vault/Session |
| CH 9 Jarvis Ready | COMPLETE | — |

### RULE 合规表

| RULE | 判定 | 证据 |
|---|---|---|
| RULE-001 Host Independence | ✅ PASS | `core/` 无任何 host 引用；依赖方向仅 HostProtocol（FINAL_VERIFICATION 项 23） |
| RULE-002 Jarvis Replaceability | ✅ PASS | TEST H：Harness→Jarvis 状态跨 Host 保留，Core 零修改（P20） |
| RULE-003 SQLite Runtime Truth | ✅ PASS | `persistence/sqlite.py` RepositorySet；JSON dual state 已消除（P1.1）；`test_no_json_dual_state` |
| RULE-004 Host 不持有 Task Truth | ✅ PASS | Host 只发 Command：`HarnessHostAdapter` → `TaskCoordinator.apply_update` → StateMachine（P1.1） |
| RULE-005 Deterministic Core | ✅ PASS | scoring/ranking/normalize/entity/constraint/policy 全部程序化；无 LLM 依赖（RULE-005 测试） |
| RULE-006 Observation/Evidence/Decision 分离 | ✅ PASS | `core/evidence/` + Decision 引用 evidence（P3/P11；`[验证] deterministic_T2 ... evidence=1条`） |
| RULE-007 External Side Effects via Gateway | ✅ PASS | 唯一执行路径 `TransactionExecutor`；SkillProtocol 无 execute（P5/P16） |
| RULE-008 Default Deny | ✅ PASS | 默认 deny + KillSwitch（P14/P16，TEST J） |
| RULE-009 Fail Closed | ✅ PASS | `DataCompleteness`/stops=-1/PARTIAL 不进 Final（SPRINT A/A.1） |
| RULE-010 Traceability | ✅ PASS | trace_id 全链路 + AuditLog + 事件可重放（P2/P4） |

---

## 一、P1 缺口（必修，全部已披露）

### 1. FR-030 — Harness `run_task_once()` 仍为 not_implemented

Requirement:
FR-030
Expected:
`HarnessHostAdapter.run_task_once()` 真实执行一次扫描并返回结果；SPAC 明确"不得保留 not_implemented"。
Actual:
`universal_agent/hosts/deepseek_harness/adapter.py:56-57` 返回 `{"task_id": task_id, "status": "not_implemented"}`，未调用任何扫描管线。
Status:
FAIL
Severity:
P1
Affected Modules:
`hosts/deepseek_harness/adapter.py`、`coordinator/scanner/*`（已有 scan 能力可复用）
Missing Work:
实现 run_task_once：按 task_id 加载 WatchTask → 走 ScanOutcome 管线（shadow/live）→ 返回结构化结果；写失败测试（RED→GREEN）。
Recommended Chapter:
CHAPTER 2（2.1）

### 2. FR-031 — Harness 通知仅写日志，未真实送达

Requirement:
FR-031
Expected:
Harness 能真正收到 OPPORTUNITY / PRICE_DROP / WATCH_FAILED / APPROVAL_REQUIRED / ACTION_RESULT 通知（非仅日志）。
Actual:
`adapter.py:70-71` `send_notification()` 仅 `log.info(...)`；DSH 侧 `dsh/uabrg-plugin.js` 无通知通道（只有 `ua_watch_scan` 工具 + scheduler 事件）。
Status:
FAIL
Severity:
P1
Affected Modules:
`hosts/deepseek_harness/adapter.py`、`dsh/uabrg-plugin.js`、`notifications/`
Missing Work:
定义 Harness 通知 sink（插件注册通知通道 → DSH 会话可见）；`send_notification` 调用真实通道；覆盖 5 类事件类型。
Recommended Chapter:
CHAPTER 2（2.2）

### 3. FR-032 — 审批固定返回 pending，无真实流转

Requirement:
FR-032
Expected:
ActionIntent → Approval Request → 持久化 → 用户 APPROVED/DENIED → 恢复 Action Pipeline；不得固定返回 pending。
Actual:
`adapter.py:73-75` `request_approval()` 固定返回 `{"approved": False, "status": "pending"}`；审批持久化在 Core 侧有（`actions/approval/`），但 Host 入口未接用户决策。
Status:
FAIL
Severity:
P1
Affected Modules:
`hosts/deepseek_harness/adapter.py`、`actions/approval/*`、`dsh/uabrg-plugin.js`
Missing Work:
Host 审批入口：请求持久化 → 用户 APPROVED/DENIED 回调 → 写入 Core 审批流 → 恢复 Action Pipeline；禁止固定 pending。
Recommended Chapter:
CHAPTER 2（2.3）

### 4. FR-033 — DSH Bridge 硬编码开发者路径

Requirement:
FR-033
Expected:
无硬编码 `/Users/<name>/...`；使用 `UA_ROOT / UA_PYTHON / UA_DATA_DIR / UA_CONFIG`；配置优先级 Plugin Config → Env → Auto Discovery → Explicit Failure；禁止 silent fallback。
Actual:
`dsh/uabrg-plugin.js:20-21` 硬编码 `UA_ROOT='/Users/huhongjie/Desktop/扫描决策类agent/universal-agent'`、`PY='/Users/huhongjie/Desktop/扫描决策类agent/.venv/bin/python'`。
Status:
FAIL
Severity:
P1
Affected Modules:
`dsh/uabrg-plugin.js`
Missing Work:
改为 `process.env.UA_ROOT || process.env.UA_PYTHON` 解析；提供 auto-discovery（相对 `__dirname` 定位仓库）+ 显式失败；写可移植性测试。
Recommended Chapter:
CHAPTER 2（2.4）

### 5. FR-191/FR-192 — 生产凭据后端未实现（macOS Keychain / Windows Credential Manager）

Requirement:
FR-191 / FR-192
Expected:
Production 支持 macOS Keychain 与 Windows Credential Manager 存储凭据。
Actual:
`security/vault.py` 为 dev 混淆（base64+XOR、固定 dev key）；无 OS Keychain / Credential Manager 后端。
Status:
NOT_IMPLEMENTED
Severity:
P1
Affected Modules:
`security/credential_vault/vault.py`
Missing Work:
实现 OS 凭据后端接口（Keychain Security Framework / WinCred），dev 混淆降级为兜底；写平台条件测试。
Recommended Chapter:
CHAPTER 8（8.1）

### 6. FR-074 — 第二/第三 Flight Live Source 未接

Requirement:
FR-074
Expected:
目标支持 Skyscanner / Ctrip / Fliggy / Tongcheng 多源；不可访问时明确 DEGRADED/UNAVAILABLE。
Actual:
Skyscanner 为唯一 Flight Live 源（P8）；Ctrip/Fliggy/Tongcheng 无 Live adapter（仅 shadow_scan replay fixtures 模拟）。
Status:
PARTIAL
Severity:
P1
Affected Modules:
`adapters/skyscanner/`、`domains/flight/`
Missing Work:
第二 Flight Live Source（Ctrip/Fliggy 优先），复用 SkillProtocol 模式 + 合规约束；跨源 Entity Resolution（FR-071）依赖多源。
Recommended Chapter:
CHAPTER 4（4.2/4.3）

### 7. FR-082 — Hotel 无真实 Live Source

Requirement:
FR-082
Expected:
完整 Hotel Pipeline：Search → Detail → Room Normalize → Availability → Policy → Price → Verify → Score → Rank（真实数据）。
Actual:
`domains/hotel/` + `coordinator/scanner/hotel.py` 已实现（政策归一化 P9），但仅 replay 数据，无真实 Hotel adapter。
Status:
PARTIAL
Severity:
P1
Affected Modules:
`domains/hotel/`、`adapters/`（无 hotel 源）
Missing Work:
接真实 Hotel 源（Booking/Ctrip 候选），完成 Live 闭环 + 对照验证。
Recommended Chapter:
CHAPTER 4（4.4）

### 8. FR-060/061/062 — 通用 HTTP/API/Browser Adapter 为空占位

Requirement:
FR-060 / FR-061 / FR-062
Expected:
正式建立通用 HTTP / API / Browser Adapter（含能力解析、健康、失败隔离）。
Actual:
`adapters/{http,api,browser}/` 仅 `__init__.py`（已核实无实现文件）。
Status:
NOT_IMPLEMENTED
Severity:
P1
Affected Modules:
`adapters/http/`、`adapters/api/`、`adapters/browser/`
Missing Work:
实现三类通用 Adapter + 能力注册 + 失败隔离测试（CH 3 Gate：Source A FAIL / B PASS / C DEGRADED 仍产出有效结果）。
Recommended Chapter:
CHAPTER 3（3.1/3.2/3.3）

### 9. FR-100/101 — Jobs 无真实 Live Source

Requirement:
FR-100 / FR-101
Expected:
跨招聘平台统一 Job Candidate + 匹配（真实数据）。
Actual:
`domains/jobs/` + JobSkillProtocol + human-only + Answer Memory 已实现（P13），但无真实招聘源 adapter（官方 Careers/LinkedIn/SEEK 均未接）。
Status:
PARTIAL
Severity:
P1
Affected Modules:
`domains/jobs/`、`adapters/`
Missing Work:
接一个真实 Job Live 源（官方 Careers 优先），完成 Discover→Normalize→Match→Decide→Prepare。
Recommended Chapter:
CHAPTER 6（6.1）

---

## 二、P2 缺口

### 10. FR-063 — Mobile Adapter Contract 未定义

Requirement:
FR-063
Expected:
第一阶段 Mobile 至少定义 Protocol（Contract）。
Actual:
`adapters/mobile/` 仅 `__init__.py`，无任何 Protocol/Contract 定义。
Status:
NOT_IMPLEMENTED
Severity:
P2
Affected Modules:
`adapters/mobile/`
Missing Work:
定义 MobileAdapter Protocol + 契约测试（不接真实移动端）。
Recommended Chapter:
CHAPTER 3（3.4）

### 11. FR-162/163 — Notification 分级与多通道未完整

Requirement:
FR-162 / FR-163
Expected:
Priority LOW/NORMAL/HIGH/URGENT；Channel 抽象 Harness/Desktop/Mobile/Webhook/Jarvis/Future。
Actual:
`notifications/dedup.py` 有 fingerprint + cooldown（持久化）；无 priority 分级、无 channel 抽象。
Status:
PARTIAL
Severity:
P2
Affected Modules:
`notifications/`
Missing Work:
NotificationService 完整化：priority 枚举 + channel 路由抽象 + 对应测试。
Recommended Chapter:
CHAPTER 5（5.x）/ 独立 Sprint

### 12. FR-164 — 通知事件类型与 SPAC 列表未对齐

Requirement:
FR-164
Expected:
事件至少含 PRICE_DROP / RARE_OPPORTUNITY / AVAILABILITY_CHANGE / WATCH_FAILED / APPROVAL_REQUIRED / ACTION_RESULT。
Actual:
`events/types.py` 仅 `OPPORTUNITY_DETECTED` 等；PRICE_DROP/RARE_OPPORTUNITY 等事件常量未定义（机会触达通过通知模块自由字符串表达）。
Status:
PARTIAL
Severity:
P2
Affected Modules:
`events/types.py`、`notifications/`
Missing Work:
补充事件类型枚举 + 通知事件映射测试。
Recommended Chapter:
CHAPTER 5

### 13. FR-073 / FR-052 / FR-053 — Skyscanner detail/verify/availability 未接真实详情页

Requirement:
FR-073 / FR-052 / FR-053
Expected:
Flight 结果 STRUCTURED（完整航段）；Skill verify/availability 真实确认。
Actual:
Skyscanner search 恒 duration-only PARTIAL（stops=-1，合规 fail-closed）；detail/verify/availability 为安全占位。
Status:
PARTIAL
Severity:
P2
Affected Modules:
`adapters/skyscanner/`
Missing Work:
接真实详情页补齐 STRUCTURED 数据（FR-073 Ranking Eligibility 依赖）。
Recommended Chapter:
CHAPTER 4（4.1 后续）

### 14. FR-102 — Jobs Application State 状态机未实现

Requirement:
FR-102
Expected:
状态：DISCOVERED / SHORTLISTED / PREPARED / NEEDS_USER / READY / SUBMITTED / FAILED。
Actual:
全包搜索无 `ApplicationState`/`application_state`（grep 验证），Job 提交被 ActionGateway 按 IRREVERSIBLE 拒绝。
Status:
NOT_IMPLEMENTED
Severity:
P2
Affected Modules:
`domains/jobs/`
Missing Work:
实现 ApplicationState 状态机 + 提交生命周期测试（受 FR-173 边界约束）。
Recommended Chapter:
CHAPTER 6（6.3）

### 15. FR-142 — Rare Opportunity 识别未显式实现

Requirement:
FR-142
Expected:
识别"明显低于历史 + 库存稀缺 + 时间窗口临近 + 高偏好"的稀有机会。
Actual:
`core/opportunity/engine.py` 有 percentile/hist_low/trend（P11）；无"稀缺库存 + 时间窗口"的稀有度显式逻辑。
Status:
PARTIAL
Severity:
P2
Affected Modules:
`core/opportunity/engine.py`
Missing Work:
稀有度评分维度（availability 稀缺 + deadline 临近）并入 OpportunityScore。
Recommended Chapter:
CHAPTER 5（5.x）

### 16. FR-110~117 等 — Railway / Ecommerce / Food 仅域骨架

Requirement:
FR-110~117（Railway）+ §21/§22（Ecommerce/Food）
Expected:
每域 Raw Contract → Normalize → Entity → Score → Skill → Source → Verify → Watch → Notification（Live）。
Actual:
P17–19 仅完成 Raw 契约 + normalize + entity_key（复用 Core）；Score/Skill/Source/Verify/Watch/Notification 未做。
Status:
PARTIAL
Severity:
P2
Affected Modules:
`domains/railway/`、`domains/ecommerce/`、`domains/food/`
Missing Work:
逐域完成剩余管线（独立测试每个小域），达成 RAILWAY_LIVE_READY / ECOMMERCE_LIVE_READY / FOOD_LIVE_READY。
Recommended Chapter:
CHAPTER 7

### 17. FR-021 / FR-014 — Outbox Dispatcher 未接 daemon 后台循环；RunLease 无 heartbeat 线程

Requirement:
FR-021 / FR-014
Expected:
Outbox Dispatcher 自动驱动 + 重试 + DLQ；RunLease 可靠续期防多进程双运行。
Actual:
`events/reliable.py` OutboxDispatcher 已实现（dispatch_once/run_forever），但 WatchDaemon 未自动驱动（拉模式）；RunLease renew 由调用方负责，无 heartbeat 后台线程。
Status:
PARTIAL
Severity:
P2
Affected Modules:
`events/reliable.py`、`coordinator/scheduler/daemon.py`、`coordinator/scheduler/runlease.py`
Missing Work:
daemon 后台循环驱动 dispatcher + RunLease heartbeat 线程。
Recommended Chapter:
CHAPTER 5 / CHAPTER 1 补强

### 18. FR-193 / FR-194 — Identity Vault / Session Broker 空占位

Requirement:
FR-193 / FR-194
Expected:
Identity Vault 独立于普通 Memory；Session Broker 独立管理外部平台 Session。
Actual:
`security/identity_vault/`、`security/session_broker/` 仅 `__init__.py`（已核实）。
Status:
NOT_IMPLEMENTED
Severity:
P2
Affected Modules:
`security/identity_vault/`、`security/session_broker/`
Missing Work:
实现 IdentityVault（独立存储域）+ SessionBroker（会话管理 + 失效恢复）。
Recommended Chapter:
CHAPTER 8（8.2/8.3）

---

## 三、P3 缺口（摘要）

- Metrics 未全链路自动埋点（`observability/registry.py` 需手动 increment）。
- Traces 无父子 span 关联图、无 OpenTelemetry 导出（`observability/tracer.py` 仅 trace_id 分组）。
- SourceHealthTracker 阈值固定（degrade_after=3），未按源差异化（FR-055 相关）。
- HOT Watch 判定来自 meta 静态标记，未由 Opportunity Engine 动态标记（FR-140 相关）。
- PreferenceLearner 固定用户 u1、学习规则简单（FR-150/152 相关，v1.3+ 计划）。

---

## 四、FR 覆盖速览（组级）

| SPAC 组 | FR | 判定 | 一句话证据 |
|---|---|---|---|
| Task Types | FR-001~006 | PASS | task_registry + WatchTask 类型（OneShot/Scheduled/Watch/ConditionWatch/Composite/MultiDomain） |
| Watch Lifecycle | §6 | PASS | `core/state_machine.py` 11 状态 + 终态 no-op（TEST B） |
| Scheduler | FR-010~015 | PASS | ZoneInfo/misfire/retry/RunLease/崩溃恢复（TEST A/C/I） |
| Persistence | §8 | PASS | `persistence/` SQLite RepositorySet（P1.1/P2） |
| Events | FR-020/021 | PASS | `events/reliable.py` EventStore+Outbox+DLQ（P2，9 项测试） |
| Harness | FR-030~034 | **PARTIAL** | 030/031/032/033 FAIL（P1，见上）；034 重启恢复依赖 SQLite（有实现，待 2.6 验收） |
| Jarvis | FR-040/041 | PASS | P20 Host Swap；capabilities 列表在 `hosts/jarvis/adapter.py:21-23` |
| Skill Runtime | FR-050~056 | PASS | SkillProtocol 6 方法、无 execute（P5） |
| Generic Adapter | FR-060~064 | **PARTIAL** | 060~063 空占位；064 Failure Isolation PASS（TEST I） |
| Flight | FR-070~074 | PASS（074 除外） | normalize/entity/scoring/eligibility 全实现（A/A.1/P8）；074 多源 PARTIAL |
| Hotel | FR-080~083 | **PARTIAL** | 082 Live 未接；083 独立失败 PASS |
| Travel Bundle | FR-090~092 | PASS | `core/bundling/` 总效用非贪心 + why_this_bundle（P10） |
| Jobs | FR-100~104 | **PARTIAL** | 100/101 Live 源未接；102 Application State 未实现；103/104 PASS（P13） |
| Railway/Ecommerce/Food | FR-110~117 等 | **PARTIAL** | 仅 Raw+normalize+entity_key（P17–19） |
| Obs/Evid/Decision | FR-130~133 | PASS | `core/evidence/` + Decision 引用 evidence + 反查链（P3） |
| Opportunity | FR-140~142 | PASS（142 除外） | percentile/trend/availability（P11）；142 rare 未显式（P2 #15） |
| Memory | FR-150~155 | PASS | MemoryDomains 8 子域 + versioned/explainable/reversible（P3/P12） |
| Notification | FR-160~164 | **PARTIAL** | 160/161 PASS（持久化 dedup+cooldown）；162/163/164 PARTIAL（P2 #11/#12） |
| Controlled Actions | FR-170~176 | PASS | L0~L4 + snapshot + slippage + idempotency + reconcile + executor（P15/P16） |
| Kill Switch | FR-180 | PASS | `actions/policy/killswitch.py` |
| Security | FR-190~194 | **PARTIAL** | 190 PASS（明文不落盘）；191/192 未实现；193/194 空占位 |

---

## 五、修复优先级建议

1. **先做 CHAPTER 2（P1×4）**：FR-030/031/032/033 —— 唯一存在 FAIL 且直接违反 SPAC 明文要求的模块；完成后 CHAPTER 2 Gate（SPAC §36 Acceptance Flow）。
2. **再补安全（P1×1）**：FR-191 macOS Keychain（FR-192 Windows 随平台条件实现）。
3. **然后多源（P1×3 + P2）**：FR-074 第二 Flight 源 → FR-082 Hotel Live → FR-071 跨源实体解析。
4. **通用 Adapter（P1×1 + P2）**：FR-060/061/062 落地 → FR-063 Mobile Protocol。
5. **Jobs Live（P1×1）**：FR-100/101 接真实源 → FR-102 Application State。
6. **新域 Live（P2）**：Railway → Ecommerce → Food（CH 7，每小域独立测试）。
7. **终态（P2/P3）**：通知分级、Rare Opportunity、Outbox daemon、IdentityVault/SessionBroker、Skyscanner 详情页、多用户。

> 每次大 Chapter 完成后：IMPLEMENT → TEST → FIX → RETEST → PASS（SPAC §44），并全量回归（§47）。
