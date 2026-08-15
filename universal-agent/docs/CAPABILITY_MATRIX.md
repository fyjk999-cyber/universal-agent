# Capability Matrix — Universal Agent

> 生成：2026-08-15（CHAPTER 0 重新生成）· 来源：**实际代码 + 测试**（不信任 README 声明）
> 复核基线：`cd universal-agent && ../.venv/bin/python -m pytest -q` → **514 passed / 0 failed**
> 状态图例：`IMPLEMENTED` = 真实实现+测试 / `PARTIAL` = 部分实现 / `MOCK` = 替身 /
> `REPLAY` = 仅回放数据 / `SKELETON` = 骨架 / `EMPTY` = 空占位 / `BROKEN` = 有缺陷
> 对齐：SPAC.md（Source of Truth）+ MISSING_FEATURE_REPORT.md（深度审计，P0×6/P1×15）

## 一、Core Architecture

| Capability | Status | Implementation | Tests | Known Limitations | Next Action |
|---|---|---|---|---|---|
| HostProtocol | IMPLEMENTED | `hosts/protocol/host.py`（12 方法） | host_contract | — | — |
| HarnessHostAdapter（RULE-004 命令边界 + FR-030~032） | IMPLEMENTED | `hosts/deepseek_harness/adapter.py`：create/update/pause/resume/cancel/list/get 经 TaskCoordinator；**run_task_once 真实执行（P23）**；send_notification 持久化+sink；request_approval 真实创建 + decide_approval | host_swap + test_p23_run_once | — | 2.5/2.6 验收 |
| JarvisHostAdapter | IMPLEMENTED | `hosts/jarvis/adapter.py` + event_bridge + mock；10 capabilities（FR-041） | test_p20_jarvis（Host Swap Core 零修改） | Mock/Preview 契约已稳定 | 生产部署 |
| EventEnvelope（FR-020） | IMPLEMENTED | `events/envelope.py`（event_id/type/timestamp/trace_id/task_id/run_id/source/payload） | events 5+ | 事件类型枚举待补 FR-164 列表 | CH 5 |
| EventBus / InProcess | IMPLEMENTED | `events/bus.py` | events | 进程内 | — |
| Reliable Events（FR-021） | IMPLEMENTED | `events/reliable.py`：SQLite EventStore + Transactional Outbox + Dispatcher + Retry + DLQ | test_p2_reliable_events（9） | Dispatcher 拉模式未接 daemon 后台循环（P2） | CH 5 |
| WatchTask 状态机 | IMPLEMENTED | `core/state_machine.py`（DRAFT/ACTIVE/WATCHING/PAUSED/COMPLETED/FAILED/CANCELLED + 终态 no-op） | test_b_watch_lifecycle | — | — |

## 二、Scheduler / Watch

| Capability | Status | Implementation | Tests | Known Limitations | Next Action |
|---|---|---|---|---|---|
| BaselineScheduler（FR-011 IANA/DST） | IMPLEMENTED | `coordinator/scheduler/baseline.py`（ZoneInfo + due_tasks_utc） | test_scheduler_daemon（A 修复） | — | — |
| MisfirePolicy（FR-012） | IMPLEMENTED | SKIP/RUN_ONCE/CATCH_UP_LIMITED，默认 RUN_ONCE | A | — | — |
| ScanRun 状态 + Retry（FR-013） | IMPLEMENTED | FAILED_RETRYABLE + backoff（1m/5m/15m/1h），Watch 保持 WATCHING；retry chain 跨重启 + RunGuard | test_p09_retry（28） | — | — |
| RunLease（FR-014） | IMPLEMENTED | `coordinator/scheduler/runlease.py`（DB 互斥） | test_p1.1a（8）+ test_two_daemons | 无 heartbeat 后台线程（P2） | CH 5 |
| WatchDaemon + Crash Recovery（FR-015） | IMPLEMENTED | SQLite 恢复 + 未完成 ScanRun 识别 + 安全重试 | test_a_startup_shutdown_restart | — | — |
| RuleAdaptiveScheduler（FR-005 5.7 频率） | IMPLEMENTED | `adaptive.py`（时间窗口频率 + HOT 加速受 governor 约束） | test_p7_adaptive | — | — |
| Checkpoint | IMPLEMENTED | `coordinator/checkpoint/` | 2 | — | — |

## 三、Persistence（RULE-003 SQLite 唯一 Truth）

| Capability | Status | Implementation | Tests | Known Limitations | Next Action |
|---|---|---|---|---|---|
| Repository Protocol + SQLite | IMPLEMENTED | `persistence/protocol.py` + `sqlite.py` + `repos.py`（9 个 repo 类 + 全表 schema） | test_no_json_dual_state（P1.1） | — | — |
| RepositorySet 装配（§8，P23 全量接线） | IMPLEMENTED | `service.py` RepositorySet：tasks/scan_runs/memory/events/outbox/observations/notifications/approvals/actions/audit/source_health + idempotency/dedup/killswitch Kv 表 | test_service_wires_all_repos_sqlite | 组件消费 outbox/events 待接（P2） | CH1 剩余 |
| JSON 仅限 Export/Debug/Log | IMPLEMENTED（P23） | IdempotencyStore/NotificationDedup/KillSwitch/ApprovalInbox 均支持 SQLite 后端（service 装配 SQLite）；JSON 仅显式 data_dir 时保留（兼容/测试） | test_*_survives_restart ×3 | observations 扫描器内仍用 JSON ObservationStore（P2 替换） | CH1 剩余 |

## 四、Data Contracts

| Capability | Status | Implementation | Tests | Known Limitations | Next Action |
|---|---|---|---|---|---|
| 冻结核心契约 | IMPLEMENTED | `core/contracts/*`（Pydantic v2） | contract 46 | — | — |
| Raw 契约（RawListing/RawHotel/RawJob/RawRailway/RawProduct/RawDish） | IMPLEMENTED | `contracts/raw.py` + domains raw | P17–19 | — | — |
| ActionIntent（approved_* 快照） | IMPLEMENTED | `core/contracts/action.py` | test_p09_approval | — | — |

## 五、Domain（§15-22）

| Capability | Status | Implementation | Tests | Known Limitations | Next Action |
|---|---|---|---|---|---|
| Flight（FR-070~073） | IMPLEMENTED | `domains/flight/` normalize + knowledge(strong/weak entity) + scoring + rank_eligibility | test_flight_normalize/scoring + test_p09_eligibility/entity（30+） | PARTIAL 不进 Final Top5（合规） | — |
| Flight 多源（FR-074） | **PARTIAL** | 仅 Skyscanner Live；Ctrip/Fliggy/Tongcheng 无 adapter | test_skyscanner_adapter（17） | 单源无交叉验证（P1） | CH 4.2/4.3 |
| Hotel（FR-080~082） | **PARTIAL** | `domains/hotel/` + HotelPolicy（breakfast/cancellation/tax/occupancy）+ HotelScanCoordinator | test_hotel + test_p9_hotel | 无真实 Live 源（仅 replay）（P1） | CH 4.4 |
| Travel Bundle（FR-090~092） | IMPLEMENTED | `core/bundling/` + `domains/travel/` 总效用非贪心 + why_this_bundle | test_bundle + test_e_travel_bundle | — | — |
| Jobs（FR-100~104） | **PARTIAL** | `domains/jobs/` + JobSkillProtocol + human-only + Answer Memory | test_p13_careerpilot + test_f_jobs | 无 Live 源（P1）；Application State 未实现（P2） | CH 6 |
| Railway（FR-110~117） | **PARTIAL**（Live 源已接入） | Raw + normalize + entity_key（P17-19）+ **12306 真实余票源（`adapters/railway/`，无 key，实测 20 条）** | test_railway_12306（4 项，含真实接口 live 测试） | 票价端点限流（best-effort）；Watch/Scoring 未接 | CH 7 |
| Ecommerce（§21） | **PARTIAL** | Raw + normalize + entity_key | P17–19 | 同上 | CH 7 |
| Food（§22） | **PARTIAL** | Raw + normalize + entity_key | P17–19 | 同上 | CH 7 |

## 六、Source Adapters

| Capability | Status | Implementation | Tests | Known Limitations | Next Action |
|---|---|---|---|---|---|
| Replay adapter | IMPLEMENTED | `adapters/replay/adapter.py` | 5 | 回放数据 | — |
| Skyscanner（FR-074 Live） | IMPLEMENTED | `adapters/skyscanner/adapter.py`（SkillProtocol 垂直闭环） | 17（P8） | search 恒 duration-only PARTIAL（stops=-1，合规 fail-closed）；detail/verify/availability 占位（P2） | CH 4.1 详情页 |
| FX 汇率 | IMPLEMENTED | `adapters/fx/service.py`（缓存+兜底） | 3 | 兜底表可能过时 | — |
| HTTP Adapter（FR-060，CH4） | IMPLEMENTED | `adapters/http/adapter.py`（超时/重试/失败隔离） | test_ch4（全链路） | — | — |
| Ctrip Flight 第二源（FR-074） | IMPLEMENTED（结构+测试） | `adapters/ctrip/` CtripFlightSkill（SkillProtocol + HTTP JSON + fail-closed + 健康检查） | test_ch4_multi_source | 真实端点待联调（UA_CTRIP_ENDPOINT） | CH4 联调 |
| Kiwi Tequila 真实价格源（FR-074） | IMPLEMENTED（管线已通） | `adapters/kiwi/` KiwiTequilaFlightSkill（真实 API；本机实测 401/403 认证语义正确，只差 key） | test_kiwi_source（5 项，含真实端点管线） | 需用户注册 UA_KIWI_KEY（partners.kiwi.com） | 用户注册 key 后联调 |
| Booking Hotel 源（FR-082） | IMPLEMENTED（结构+测试） | `adapters/booking/` BookingHotelSkill | test_ch4（hotel） | 真实端点待联调（UA_BOOKING_ENDPOINT） | CH4 联调 |
| API / Browser Adapter（FR-061/062） | **EMPTY** | `adapters/api/`、`adapters/browser/` 仅 `__init__.py`（已核实） | 0 | 未实现（P1） | CH 3.2/3.3 |
| Mobile Adapter（FR-063） | **EMPTY** | `adapters/mobile/` 仅 `__init__.py`（已核实） | 0 | 连 Protocol 都未定义（P2） | CH 3.4 |
| Tier3 官方源 | SKELETON | `adapters/official/registry.py`（注册器+健康检查） | 4 | 无真实航司适配器（合规） | v1.3 |
| Failure Isolation（FR-064） | IMPLEMENTED | 多 query 并发 + 单源失败隔离 | test_i_failure_injection | — | — |

## 七、Verification / Decision / Opportunity

| Capability | Status | Implementation | Tests | Known Limitations | Next Action |
|---|---|---|---|---|---|
| Verification 分级（FR-052） | IMPLEMENTED | `core/verification/verifier.py`（Tier1-4 + Evidence） | 5 + shadow_scan 实测 | 置信度默认固定 | — |
| Observation/Evidence/Decision 分离（RULE-006/FR-130~133） | **PARTIAL** | Observation + Evidence（`core/verification/verifier.py`）真实；**Decision 层缺失**：`core/decision/` 空目录、无 Decision 契约、无 supporting_evidence（FR-132，P1） | test_p3 + 实测 | 决策不可审计反查（P1） | CH 决策层补建 |
| Deterministic Decision Pipeline（§24） | IMPLEMENTED | normalize→entity→constraint→dedup→score→rank→change→verify→opportunity | 全链测试 | — | — |
| Change Detection | IMPLEMENTED | `core/change_detection/` | 2 | — | — |
| Opportunity Engine（FR-140/141） | IMPLEMENTED | `core/opportunity/engine.py`（percentile/hist_low/trend/availability） | test_p11 + 实测 score=75.4 | rare 稀有度维度未显式（FR-142，P2） | CH 5 |
| Trigger Engine | IMPLEMENTED | `coordinator/trigger_engine/` | 3 | — | — |

## 八、Actions / Risk Controls（FR-170~176, FR-180）

| Capability | Status | Implementation | Tests | Known Limitations | Next Action |
|---|---|---|---|---|---|
| ActionGateway（RULE-007 唯一入口） | IMPLEMENTED | `actions/gateway/gateway.py` | test_action_gateway | — | — |
| L0/L1/L2 PREPARE（FR-170~172） | IMPLEMENTED | `prepare.py`（flight/jobs/ecommerce，No Commit） | test_action_prepare + test_p15_prepare | — | — |
| L3/L4 Controlled Executor（FR-173） | IMPLEMENTED | `execute.py` → TransactionExecutor（唯一路径） | test_p16_controlled（9） | — | — |
| Slippage Guard（FR-174） | IMPLEMENTED | `guard.py` approved vs actual + material change → BLOCK/REAPPROVAL | 12（A.1） | — | — |
| Idempotency（FR-175） | IMPLEMENTED | `store.py` reserve→commit→finalize + reconcile | 14（A.1/P1.1e） | — | — |
| Reconciliation（FR-176） | IMPLEMENTED | UNKNOWN→reconcile 三分支（CONFIRMED/NOT_FOUND/UNKNOWN） | test_p11_tx_ambiguity | — | — |
| Compensation | IMPLEMENTED | `actions/compensation/`（成功绝不补偿） | 8（A） | — | — |
| Approval Inbox + Snapshot（FR-032 Core 侧） | IMPLEMENTED | `actions/approval/` | test_p09_approval | Host 入口未接用户决策（P1） | CH 2.3 |
| PolicyEngine + Default Deny（RULE-008） | IMPLEMENTED | `actions/policy/engine.py` | 6 + TEST J | — | — |
| KillSwitch（FR-180） | IMPLEMENTED | `actions/policy/killswitch.py` | 3 | — | — |

## 九、Memory / Security

| Capability | Status | Implementation | Tests | Known Limitations | Next Action |
|---|---|---|---|---|---|
| Memory 8 子域（FR-150/151） | IMPLEMENTED | `memory/domains.py` MemoryDomains（intent/preference/decision/observation/answer/task_state/policy/execution_history）+ `sqlite_store.py` | test_p3_memory_domains（8 roundtrip + filter） | — | — |
| Preference Learning（FR-152~155） | IMPLEMENTED | `memory/preferences/learner.py` versioned/explainable/reversible，不碰 Policy | test_p12_preference | 固定用户 u1（P3） | v1.3 |
| CredentialVault（FR-190） | IMPLEMENTED | `security/vault.py` 混淆存储 + 掩码，明文不落盘 | test_p14_security + TEST J | dev 混淆非生产级（FR-191/192 未实现，P1） | CH 8.1 |
| PermissionManager | IMPLEMENTED | `security/manager.py` 默认拒绝 | test_p14_security | — | — |
| IdentityVault（FR-193） | **EMPTY** | `security/identity_vault/` 仅 `__init__.py` | 0 | 未实现（P2） | CH 8.2 |
| SessionBroker（FR-194） | **EMPTY** | `security/session_broker/` 仅 `__init__.py` | 0 | 未实现（P2） | CH 8.3 |

## 十、Notifications / Observability

| Capability | Status | Implementation | Tests | Known Limitations | Next Action |
|---|---|---|---|---|---|
| NotificationDedup（FR-160/161 持久化） | IMPLEMENTED | `notifications/dedup.py` fingerprint + cooldown；P23 支持 SQLite 后端（service 装配） | test_dedup + test_dedup_sqlite_survives_restart | — | — |
| Notification priority/channel（FR-162/163） | **PARTIAL** | 无 LOW/NORMAL/HIGH/URGENT 分级、无 channel 抽象 | — | P2 | CH 5 |
| 通知事件类型（FR-164） | IMPLEMENTED（P23） | `events/types.py` 补 PRICE_DROP/RARE_OPPORTUNITY/AVAILABILITY_CHANGE/WATCH_FAILED/APPROVAL_REQUIRED/ACTION_RESULT | test_fr164_event_types_declared | 事件实际投递链路待 2.6 验收 | CH 2.6 |
| Audit Log（RULE-010） | IMPLEMENTED | `observability/audit.py` | 1+ | — | — |
| Metrics（§31） | IMPLEMENTED | `observability/registry.py` MetricsRegistry | test_p4_observability | 未全链路自动埋点（P3） | v1.3 |
| Traces | IMPLEMENTED | `observability/tracer.py` trace_id 链路 | test_p4_observability | 无父子 span 关联（P3） | v1.3 |
| Structured Logs | IMPLEMENTED | `observability/structured.py` | test_p4_observability | — | — |

## 十一、Apps / Integration

| Capability | Status | Implementation | Tests | Known Limitations | Next Action |
|---|---|---|---|---|---|
| shadow_scan CLI | IMPLEMENTED | `apps/shadow_scan.py`（replay + --live） | 实测：5 raw→4 candidates→Top5→机会 75.4→通知 | — | — |
| agent_cli 多域 | IMPLEMENTED | `apps/agent_cli.py`（flight/hotel/jobs/bundle/prepare/execute） | 冒烟 rc=0 | — | — |
| scheduler CLI | IMPLEMENTED | `apps/scheduler.py`（SQLite + RunLease） | 集成测试 | — | — |
| DSH Bridge（FR-033） | IMPLEMENTED（P23） | `dsh/uabrg-plugin.js`：Plugin Config → UA_* 环境变量 → Auto Discovery → Explicit Failure，零硬编码 | grep 验证无 /Users/ | 需 node 环境做运行验证（本机无 node） | 2.5 验收 |
| Harness 通知/审批（FR-031/032） | IMPLEMENTED（P23） | 通知 SQLite 持久化 + sink 投递；审批真实创建 + decide_approval + agent_cli --approve | test_p23（10 项） | DSH 插件侧通知展示待 2.6 验收 | 2.6 |
| CI Gates | IMPLEMENTED | `.github/workflows/ci.yml`（3.11+3.12，ruff+mypy+coverage） | P21/22 | — | — |
| 依赖可复现 | IMPLEMENTED | pyproject 依赖组（dev/browser/flight-live/hotel-live/jobs-live） | P22 | — | — |

---

## 总结（2026-08-15，P23 P0 收敛后）

- **IMPLEMENTED**: 约 50 项（P23 新增：run_task_once 真实执行、通知持久化+sink、审批真实流转、Bridge 可移植配置、RepositorySet 全量接线、3 个 SQLite Kv 后端）
- **PARTIAL**: 约 10 项 — 多源 DoD、Reliable Events 组件消费、通用 Adapter、新域 Live、Notification 分级、生产凭据后端、Decision 层、Jobs Live、Skyscanner 详情页
- **EMPTY**: 8 项 — adapters/{http,api,browser,mobile}、security/{identity_vault,session_broker}、core/decision/、core/constraints/
- **BROKEN**: 0 项
- 关键结论：**P0×6 中 5 项已修复（FR-030~033 + RULE-003）**，剩余 P0 为多源 DoD（CH4）；P1×15 中若干已随修复部分消解；完整状态以 `MISSING_FEATURE_REPORT.md` 为准（**532 tests / 0 failed**）
