# Capability Matrix — Universal Agent

> 生成：2026-08-14 · 来源：**实际代码 + 测试**（不信任 README 声明）
> 状态图例：`IMPLEMENTED` = 真实实现+测试 / `PARTIAL` = 部分实现 / `MOCK` = 替身 /
> `REPLAY` = 仅回放数据 / `SKELETON` = 骨架 / `EMPTY` = 空占位 / `BROKEN` = 有缺陷

## 一、Core Architecture

| Capability | Status | Implementation | Tests | Live/Replay | Known Limitations | Next Action |
|---|---|---|---|---|---|---|
| HostProtocol（§9） | IMPLEMENTED | `hosts/protocol/host.py` 12 方法 | host_contract 3 项 | n/a | Host 同时负责部分 task 状态 | P4 收敛 |
| Harness Adapter | IMPLEMENTED | `hosts/deepseek_harness/adapter.py` | host_swap 2 项 | Replay | 保存 task 真相（P1 消除） | P1.1 |
| Jarvis Adapter | MOCK | `hosts/jarvis/*` | host_swap | Replay | 仅 mock，非真服务 | P4.4 |
| EventEnvelope（§5） | IMPLEMENTED | `events/envelope.py` 8 字段 | 5 项 | n/a | 缺 correlation/causation/run_id | P3 |
| InProcessEventBus | IMPLEMENTED | `events/bus.py` | 5 项 | n/a | 非可靠持久事件 | P3 outbox |
| WatchTask 状态机（§14） | IMPLEMENTED | `core/state_machine.py` 11 状态 | 10 项 | n/a | — | — |

## 二、Scheduler / Watch

| Capability | Status | Implementation | Tests | Live/Replay | Known Limitations | Next Action |
|---|---|---|---|---|---|---|
| BaselineScheduler（§15） | **PARTIAL** | `coordinator/scheduler/baseline.py` | 4 项 | Replay | **BUG：忽略 task.timezone；用固定 timezone 拼接；无 DST** | **P0.1** |
| WatchDaemon | **PARTIAL** | `coordinator/scheduler/daemon.py` | 5 项 | Replay | **BUG：due_tasks 用 HH:MM 字符串比较；无 misfire；失败→Watch FAILED** | **P0.1/P0.2** |
| due_tasks | **BROKEN** | `task_registry/registry.py:71` | 1 项 | Replay | **字符串 `"09:00"<="21:00"` 字典序比较，跨天错** | **P0.1** |
| ScanRun 状态 | EMPTY | — | 0 | — | **无独立运行状态，平台失败杀死 Watch** | **P0.2** |
| AdaptiveScheduler | SKELETON | `adaptive.py` | 0 | — | 仅接口 + NoOp | P9 |
| Checkpoint（§60） | IMPLEMENTED | `checkpoint.py` | 2 项 | Replay | JSON 持久化 | P1 SQLite |

## 三、Data Contracts

| Capability | Status | Implementation | Tests | Live/Replay | Known Limitations | Next Action |
|---|---|---|---|---|---|---|
| 13 核心契约（§12） | IMPLEMENTED | `core/contracts/*` | 46 项 | n/a | TaskSpec.search_space 仍 Dict | P6 强类型 |
| RawListing/RawHotel/RawJob | IMPLEMENTED | `contracts/raw.py` | 包含于上 | Replay | — | — |
| ActionIntent | IMPLEMENTED | `contracts/action.py` | 4 项 | n/a | **缺 approved_quote/offer/price/expiry 字段** | **P0.3** |
| SearchSpec 强类型 | EMPTY | — | 0 | — | 依赖 Dict[str,Any] | P6 |

## 四、Domain

| Capability | Status | Implementation | Tests | Live/Replay | Known Limitations | Next Action |
|---|---|---|---|---|---|---|
| Flight normalize | IMPLEMENTED | `domains/flight/normalize.py` | 8 项 | Replay | — | — |
| Flight entity_key | **BROKEN** | `knowledge.py` | 3 项 | Replay | **航班号缺失时错误合并同日期同路线** | **P0.7** |
| Flight scoring | IMPLEMENTED | `scoring.py` | 5 项 | Replay | — | — |
| Hotel domain | IMPLEMENTED | `domains/hotel/*` | 9 项 | Replay | Room/meal 归一化待完整 | P13 |
| Jobs domain | IMPLEMENTED | `domains/jobs/*` | 12 项 | Replay | 真实源未接 | P14 |
| Travel Bundle（§28） | IMPLEMENTED | `domains/travel/bundle.py` + `core/bundling` | 5 项 | Replay | 仅 Flight+Hotel | — |
| Railway/Ecommerce/Food | EMPTY | 占位目录 | 0 | — | 未实现 | P15 |

## 五、Source Adapters

| Capability | Status | Implementation | Tests | Live/Replay | Known Limitations | Next Action |
|---|---|---|---|---|---|---|
| Replay adapter（§47） | IMPLEMENTED | `adapters/replay/` | 5 项 | Replay | 回放数据 | — |
| Skyscanner（§62） | **PARTIAL** | `adapters/skyscanner/adapter.py` | 12 项 | **Live** | **硬编码 stops=0/无 segments/数据不完整仍评分** | **P0.6** |
| FX 汇率 | IMPLEMENTED | `adapters/fx/service.py` | 3 项 | Live | 兜底表可能过时 | — |
| Tier3 官方源 | SKELETON | `adapters/official/` | 4 项 | Replay | NoOp/Stub，无真实航司 | P12.3 |
| Api/Http/Browser/Mobile adapter | EMPTY | 占位目录 | 0 | — | 未实现 | P7 |

## 六、Verification / Opportunity

| Capability | Status | Implementation | Tests | Live/Replay | Known Limitations | Next Action |
|---|---|---|---|---|---|---|
| Verification 分级（§31） | IMPLEMENTED | `core/verification/verifier.py` | 5 项 | Replay | 置信度固定默认 | P12 |
| Opportunity（§32） | IMPLEMENTED | `core/opportunity/engine.py` | 3 项 | Replay | 规则版，无趋势/预测 | P10 |
| Change Detection | IMPLEMENTED | `core/change_detection/` | 2 项 | Replay | — | — |
| Trigger（§33） | IMPLEMENTED | `coordinator/trigger_engine/` | 3 项 | Replay | — | — |

## 七、Actions / Risk Controls

| Capability | Status | Implementation | Tests | Live/Replay | Known Limitations | Next Action |
|---|---|---|---|---|---|---|
| ActionGateway L0/L1 | IMPLEMENTED | `actions/gateway/gateway.py` | 5 项 | n/a | — | — |
| ActionPreparer L2（§65） | IMPLEMENTED | `prepare.py` | 5 项 | n/a | — | — |
| ControlledExecutor L3/L4 | IMPLEMENTED | `execute.py` | 9 项 | n/a | — | — |
| SlippageGuard（§39） | **BROKEN** | `actions/slippage/guard.py` | 3 项 | n/a | **调用方自比较 confirmed vs confirmed** | **P0.3** |
| Compensation（§37/§40） | **BROKEN** | `actions/compensation/manager.py` | 3 项 | n/a | **成功路径也调 compensate** | **P0.4** |
| Idempotency（§38） | **PARTIAL** | `actions/idempotency/store.py` | 2 项 | n/a | **无 reserve/finalize/reconcile** | **P0.5** |
| ApprovalInbox（§41） | IMPLEMENTED | `actions/approval/inbox.py` | 3 项 | n/a | 未接 GUI | — |
| PolicyEngine | IMPLEMENTED | `actions/policy/engine.py` | 6 项 | n/a | — | — |
| KillSwitch | IMPLEMENTED | `actions/policy/killswitch.py` | 3 项 | n/a | — | — |
| AuditLog（§50） | IMPLEMENTED | `observability/audit/audit.py` | 1 项 | n/a | — | — |

## 八、Memory / Persistence

| Capability | Status | Implementation | Tests | Live/Replay | Known Limitations | Next Action |
|---|---|---|---|---|---|---|
| MemoryStore | IMPLEMENTED | `memory/store.py` | 4 项 | Replay | JSON | P1.2 SQLite |
| ObservationStore | IMPLEMENTED | `memory/observations/` | 集成内 | Replay | JSON | P1 |
| Intent/Preference/Decision/Answer/Policy/ExecHistory | **EMPTY** | 8 个占位目录 | 0 | — | **只有 memory/observations 有实现** | P2 |
| CredentialVault/SessionBroker/IdentityVault/Permissions | **EMPTY** | `security/` 占位 | 0 | — | **§42 未实现** | P16 |
| SQLite 持久化 | EMPTY | — | 0 | — | 全部 JSON | P1 |
| Repository Protocol | EMPTY | — | 0 | — | — | P1 |

## 九、Events / Observability

| Capability | Status | Implementation | Tests | Live/Replay | Known Limitations | Next Action |
|---|---|---|---|---|---|---|
| Transactional Outbox | EMPTY | — | 0 | — | 无可靠事件 | P3 |
| Metrics | EMPTY | `observability/metrics/` 占位 | 0 | — | 无指标 | P17 |
| Traces | EMPTY | `observability/traces/` 占位 | 0 | — | trace_id 存在于 outcome，未持久化 | P17 |
| Logs 分离 | EMPTY | `observability/logs/` 占位 | 0 | — | — | P17 |

## 十、Notification / Scheduler Persistence

| Capability | Status | Implementation | Tests | Live/Replay | Known Limitations | Next Action |
|---|---|---|---|---|---|---|
| NotificationDedup（§34） | IMPLEMENTED | `notifications/dedup.py` | 4 项 | Replay | **内存态，重启忘** | **P11** |
| 调度持久化 | PARTIAL | TaskRegistry/Checkpoint JSON | 集成内 | Replay | JSON | P1 |

## 十一、Apps / Integration

| Capability | Status | Implementation | Tests | Live/Replay | Known Limitations | Next Action |
|---|---|---|---|---|---|---|
| shadow_scan CLI | IMPLEMENTED | `apps/shadow_scan.py` | 冒烟 | Replay/Live | — | — |
| agent_cli 多域 | IMPLEMENTED | `apps/agent_cli.py` | 冒烟 | Replay | — | — |
| scheduler CLI | IMPLEMENTED | `apps/scheduler.py` | 冒烟 | Replay | 含 P0.1 bug | P0.1 |
| DSH Bridge | IMPLEMENTED | `dsh/uabrg-plugin.js` | 实测 | Live | **硬编码 /Users/ 路径** | **P4.1** |

---

## 总结

- **IMPLEMENTED**: 约 40 项（有实现+测试）
- **BROKEN（P0 必修）**: 5 项 — due_tasks 字符串比较 / entity_key 错误合并 / Slippage 自比较 / Compensation 成功补偿 / daemon 失败杀 Watch
- **PARTIAL（P0）**: 3 项 — BaselineScheduler 时区 / ScanRun 缺失 / Idempotency 无 reconcile / Skyscanner fail-open
- **EMPTY（后续）**: Memory 子域、Security、Metrics/Traces、SQLite、Outbox、SearchSpec 强类型等
