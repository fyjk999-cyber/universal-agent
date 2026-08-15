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
| ScanRun 状态 + Retry | IMPLEMENTED | `scanrun.py` + `daemon._retry_failed_runs` + `runguard.py` | 28 项 | Replay | retry 由 next_retry_at 驱动，backoff 跨重启，RunGuard 防双启动 | — |
| RunLease（DB 防双运行，P1.1） | IMPLEMENTED | `coordinator/scheduler/runlease.py` | 8 项 | n/a | 多进程互斥；无 heartbeat 后台线程 | P3 |
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
| Flight entity_key | IMPLEMENTED | `knowledge.py` strong/weak + `_has_complete_segments` | 17 项 | Replay | round-trip 双方向非空才 Strong；空/单程/缺字段不 Strong | — |
| Flight scoring + Ranking Gate | IMPLEMENTED | `scoring.py` + `rank_eligibility` | 13 项 | Replay | PARTIAL 不进 Final Top5，只进 preliminary | — |
| Hotel domain | IMPLEMENTED | `domains/hotel/*` | 9 项 | Replay | Room/meal 归一化待完整 | P13 |
| Jobs domain | IMPLEMENTED | `domains/jobs/*` | 12 项 | Replay | 真实源未接 | P14 |
| Travel Bundle（§28） | IMPLEMENTED | `domains/travel/bundle.py` + `core/bundling` | 5 项 | Replay | 仅 Flight+Hotel | — |
| Railway/Ecommerce/Food | EMPTY | 占位目录 | 0 | — | 未实现 | P15 |

## 五、Source Adapters

| Capability | Status | Implementation | Tests | Live/Replay | Known Limitations | Next Action |
|---|---|---|---|---|---|---|
| Replay adapter（§47） | IMPLEMENTED | `adapters/replay/` | 5 项 | Replay | 回放数据 | — |
| Skyscanner（§62） | IMPLEMENTED | `adapters/skyscanner/adapter.py` | 17 项 | Live | search 恒 PARTIAL（duration-only 非 STRUCTURED），stops 未知=-1 | — |
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
| SlippageGuard（§39） | IMPLEMENTED | `guard.py` approved vs actual | 12 项 | n/a | 材料变化（行李/日期/币种）→ BLOCK | — |
| Compensation（§37/§40） | IMPLEMENTED | `transaction.py` 成功绝不补偿 | 8 项 | n/a | 仅 FAIL/UNKNOWN 补偿 | — |
| Idempotency（§38） | IMPLEMENTED | `store.py` + `transaction.reconcile` | 14 项 | n/a | RESERVED/COMMITTED/UNKNOWN 需 reconcile；crash 不二次执行 | — |
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
| 调度持久化 | IMPLEMENTED | SQLite TaskRepository（唯一 Runtime Truth） | 集成内 | Replay | JSON 已移除 | — |

## 十一、Apps / Integration

| Capability | Status | Implementation | Tests | Live/Replay | Known Limitations | Next Action |
|---|---|---|---|---|---|---|
| shadow_scan CLI | IMPLEMENTED | `apps/shadow_scan.py` | 冒烟 | Replay/Live | — | — |
| agent_cli 多域 | IMPLEMENTED | `apps/agent_cli.py` | 冒烟 | Replay | — | — |
| scheduler CLI | IMPLEMENTED | `apps/scheduler.py` | 冒烟 | Replay | 含 P0.1 bug | P0.1 |
| DSH Bridge | IMPLEMENTED | `dsh/uabrg-plugin.js` | 实测 | Live | **硬编码 /Users/ 路径** | **P4.1** |

---

## 总结

- **IMPLEMENTED**: 约 44 项（有实现+测试；P1.1 新增 RunLease/UniversalAgentService/Host 命令边界）
- **BROKEN（P0 必修）**: 5 项 — due_tasks 字符串比较 / entity_key 错误合并 / Slippage 自比较 / Compensation 成功补偿 / daemon 失败杀 Watch
- **PARTIAL（P0）**: 2 项 — BaselineScheduler 时区 / Skyscanner fail-open
- **EMPTY（后续）**: Memory 子域、Security、Metrics/Traces、SQLite、Outbox、SearchSpec 强类型等
