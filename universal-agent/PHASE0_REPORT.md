# PHASE 0 + PHASE 1 skeleton — 验收报告

> 生成日期：2026-08-14
> 环境：Python 3.12.13 · pydantic 2.13.4 · pytest 9.1.1 · pytest-asyncio

---

## PHASE COMPLETED — PHASE 0（契约地基）+ PHASE 1 skeleton（事件运行时 + Watch 引擎）

**Implemented**
- 全部数据契约（Pydantic v2，extra=forbid）：TaskSpec / WatchTask / Candidate / CandidateEnvelope / Offer / Quote / Observation / Evidence / VerificationResult / Confidence / ScoreResult / OpportunityScore / TriggerEvent / ActionPlan / ActionIntent / ActionResult / MemoryRecord / MemoryQuery / SkillManifest / MarketplaceManifest
- Event 系统：EventEnvelope（§5 八个字段全齐）/ EventType（§6 全部 31+ 事件）/ EventBusProtocol / InProcessEventBus（handler 失败不崩溃，§48）
- Host 抽象：HostProtocol（12 方法，§9）/ NotificationProvider / ApprovalProvider / HarnessHostAdapter / HarnessEventBridge / MockJarvisHostAdapter / JarvisEventBridge
- WatchTask 显式状态机（§14，11 状态 + 合法转移表 + 终端态）
- MemoryStore（§16/§17，Scope 化 + JSON 持久化）
- SkillRegistry / MarketplaceRegistry + Capability 强制（§43）
- Action Gateway（§35/§36/§38/§40，V1 仅 L0/L1，L2+ 硬阻塞，idempotency_key 强制，IRREVERSIBLE 拒绝）
- NotificationDedup（§34，fingerprint + cooldown）
- TaskRegistry / BaselineScheduler / AdaptiveScheduler(接口) / WatchManager / Checkpoint / 任务 YAML loader
- Queenstown 验收任务 `tasks/queenstown-travel-watch.yaml`（§67/§70）

**Contracts added**
- `core/contracts/`：base, task, candidate, observation, scoring, action, memory, registry（13 个契约模块）
- `events/`：types, envelope, protocol, bus
- `hosts/protocol/`：host, notification
- `core/state_machine.py`（状态机契约）

**Tests** — **90 passed, 0 failed**
| 区域 | 数量 | 内容 |
|---|---|---|
| contract | 46 | 数据契约 / Event / Host / Registry / Queenstown 任务 |
| unit | 28 | 状态机 / Scheduler / Dedup / ActionGateway / Memory |
| integration | 7 | WatchManager 生命周期 / 重启恢复 / 事件桥 |
| migration | 2 | **Jarvis Host Swap（§46/§73）** |
| failure_injection | 7 | 损坏状态恢复 / 重复事件 / 乱序事件 / 畸形输入 |

**Coverage（关键路径）**
- EventBus：正常 / handler 异常 / 重复事件 / 乱序事件 / close 后 publish —— 覆盖
- 状态机：主线 6 跳 / 非法转移 / 终端态 / PAUSED↔WATCHING / FAILED 重试 —— 覆盖
- Host Swap：Harness 建任务存 Memory → 停 → Jarvis 同目录启动 → 恢复任务与 Memory → 通知 —— 覆盖（0 Core 修改）
- Registry Capability：execute_order=false 时拒绝 —— 覆盖

**Known limitations**
- Harness 与 Jarvis adapter 目前共用 JSON 文件持久化（Phase 1 简化，非真实 Harness 服务）
- run_task_once 返回 not_implemented（真实扫描管线在 PHASE 2 接入）
- AdaptiveScheduler 仅为接口 + NoOp（按计划 Phase B 再做）
- 通知只经日志输出，未接 GUI/桌面通道（Phase 1 骨架）
- 无 DB/Redis/消息队列（按 §58 第一阶段禁止过重基础设施）

**Security status**
- 无真实支付 / 无自动购票 / 无凭据存取 / L2+ 全部硬阻塞 / IRREVERSIBLE 拒绝
- 未创建 security/credential_vault 等实现（仅目录占位，符合 Phase 0）
- Action Gateway 是唯一副作用通道（RULE 6），已测试强制

**Host coupling audit**
- `grep` Core（core/events/memory/coordinator/registry/actions/notifications）→ hosts/harness import：**CLEAN ✓**
- Core 只依赖 `HostProtocol`（hosts/protocol/），从未 import 具体 adapter

**Migration compatibility**
- `tests/migration/test_host_swap.py` 通过：Harness → Jarvis 交换，0 Core 修改
- 验收问题"如果切换 Jarvis 是否需要改 Core？"答案：**NO ✓**

**Next phase**
- **PHASE 2 — Flight Shadow Vertical Slice**：TaskSpec → Scan → Normalize → Candidate → Offer → Quote → Dedup → Score → Observation → Top5 → Notify（SHADOW MODE，不购买）

---

## 交付输出（§76 要求的 11 项）

### 1. 创建/修改文件清单

**新增（核心，均在 `universal-agent/` 下）**
```
pyproject.toml
README.md
universal_agent/__init__.py
universal_agent/core/__init__.py
universal_agent/core/state_machine.py
universal_agent/core/contracts/{__init__,base,task,candidate,observation,scoring,action,memory,registry}.py
universal_agent/events/{__init__,types,envelope,protocol,bus}.py
universal_agent/hosts/__init__.py
universal_agent/hosts/protocol/{__init__,host,notification}.py
universal_agent/hosts/deepseek_harness/{__init__,adapter,event_bridge}.py
universal_agent/hosts/jarvis/{__init__,adapter,event_bridge,mock,README.md}.py/.md
universal_agent/coordinator/__init__.py
universal_agent/coordinator/task_registry/{__init__,registry,loader}.py
universal_agent/coordinator/scheduler/{__init__,baseline,adaptive}.py
universal_agent/coordinator/watch_manager/{__init__,manager}.py
universal_agent/coordinator/checkpoint/{__init__,checkpoint}.py
universal_agent/memory/{__init__,store}.py
universal_agent/registry/{__init__,registry}.py
universal_agent/actions/__init__.py
universal_agent/actions/gateway/{__init__,gateway}.py
universal_agent/notifications/{__init__,dedup}.py
tasks/queenstown-travel-watch.yaml
tests/{conftest,__init__}.py
tests/contract/{test_data_contracts,test_event_contract,test_host_contract,test_queenstown_task,test_registry_contract}.py
tests/unit/{test_state_machine,test_scheduler,test_dedup,test_memory,test_action_gateway}.py
tests/integration/{test_watch_manager,test_event_bridge}.py
tests/migration/test_host_swap.py
tests/failure_injection/test_failure_injection.py
```
另按 §57 创建了完整目录骨架（domains/* / adapters/* / security/* / observability/* / coordinator 子模块等），以 `__init__.py` 占位。

### 2. 最终目录树
见本文件下方附录（或 `find universal-agent -type f`）。

### 3. 数据契约（冻结于 core/contracts/，全部 Pydantic v2 + extra=forbid）
| 契约 | 关键字段 |
|---|---|
| TaskSpec v1 | id / type(5种) / domain / schema_version / lifecycle / schedule / search_space / notify_if |
| WatchTask v1 | TaskSpec + state / version / next_scan_at / scan_count / notified_fingerprints / history |
| Candidate | candidate_id / domain / entity_key / attributes / source_ids / first_seen_at |
| CandidateEnvelope | candidate + observed_at + source |
| Offer | offer_id / candidate_id / marketplace_id / terms / url |
| Quote | quote_id / offer_id / price(Money) / observed_at / method / confidence |
| Observation | observation_id / kind / value / observed_at / evidence_refs |
| Evidence | field / value / source / method / snapshot_reference / confidence |
| VerificationResult | Confidence(5项) + evidence + verified_by + passed |
| ScoreResult / OpportunityScore | components / total_score / historical_low / drops / percentile |
| TriggerEvent | rule / matched / severity / reason |
| ActionPlan / ActionIntent / ActionResult | intents / idempotency_key / level / reversibility / slippage |
| MemoryRecord | scope(GLOBAL/DOMAIN/TASK/SESSION) / domain / task_id / key / value / version |
| SkillManifest / MarketplaceManifest | capabilities dict / trust / health |

### 4. Event Contract（events/）
```json
{
  "event_id": "evt_...", "event_type": "...", "schema_version": "1.0",
  "trace_id": "...", "task_id": "...", "source": "...",
  "created_at": "...", "payload": {}
}
```
全部 31 个业务事件 + EVENT_FAILED（§6）已注册；EventBusProtocol 可被 Redis Streams/NATS/Kafka 替换。

### 5. Host Contract（hosts/protocol/host.py）
`create_task / update_task / pause_task / resume_task / cancel_task / run_task_once / list_tasks / get_task / send_notification / request_approval / get_host_user_context / publish_event`（§9 全齐）。

### 6. Watch State Machine（core/state_machine.py）
```
DRAFT→ACTIVE→WATCHING→MATCH_FOUND→NOTIFIED→ACTION_PENDING→FULFILLED
PAUSED↔(ACTIVE|WATCHING)   CANCELLED/EXPIRED 终端   FAILED→(ACTIVE|WATCHING) 重试
```
非法转移抛 TransitionError；无 is_active 布尔。

### 7. Memory Contract（memory/store.py + core/contracts/memory.py）
Scope 强制（GLOBAL/DOMAIN/TASK/SESSION），upsert 自动 version+1，query 过滤，JSON 持久化，重启可恢复。

### 8. 测试结果
**90 passed in 0.39s**（contract 46 / unit 28 / integration 7 / migration 2 / failure_injection 7），详见上方表格。

### 9. Harness 耦合审计
**CLEAN**：Core 全部模块（core/events/memory/coordinator/registry/actions/notifications）对 hosts/harness 的真实 import 为零（grep 验证，仅注释/文档字符串提到"Harness"字样）。

### 10. Jarvis 迁移准备度
**READY**：MockJarvisHostAdapter 已实现完整 HostProtocol，Jarvis 9 项预留能力已声明（voice_intent/desktop_notification/mobile_notification/approval_request/task_status/memory_query/watch_query/action_status/agent_health），`tests/migration/test_host_swap.py` 验证 Harness→Jarvis 交换后任务与 Memory 无损恢复、通知可用，Core 零修改。

### 11. Phase 1 建议
- PHASE 2 优先接真实扫描数据源（先 Tier1 结构化源，再 OTA verify，禁止全平台完整结算验证）
- 先为 Flight Domain 实现 QueryPlan/SourcePlan 与 Entity Resolution
- 扫描结果落 ObservationStore（事实层），再叠 Opportunity/Trigger
- 保持 Shadow Mode，L2 PREPARE 接口可建但保持硬阻塞，直到 Idempotency/Slippage/Approval/Audit/Compensation 全绿
- 每轮 Watch 记录 trace_id，串起 Scan→Candidate→Offer→Verify→Decision→Notify，供 Replay

---

## 附录：最终目录树（非空文件）
```
universal-agent/
├── pyproject.toml
├── README.md
├── tasks/queenstown-travel-watch.yaml
├── universal_agent/
│   ├── __init__.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── state_machine.py
│   │   └── contracts/{__init__,base,task,candidate,observation,scoring,action,memory,registry}.py
│   ├── events/{__init__,types,envelope,protocol,bus}.py
│   ├── hosts/
│   │   ├── protocol/{host,notification,__init__}.py
│   │   ├── deepseek_harness/{adapter,event_bridge,__init__}.py
│   │   └── jarvis/{adapter,event_bridge,mock,README.md,__init__}.py
│   ├── coordinator/
│   │   ├── task_registry/{registry,loader,__init__}.py
│   │   ├── scheduler/{baseline,adaptive,__init__}.py
│   │   ├── watch_manager/{manager,__init__}.py
│   │   ├── checkpoint/{checkpoint,__init__}.py
│   │   └── (intent/trigger_engine/deadline/query_planner/source_planner/resources/priority/dedup) 占位
│   ├── memory/{store,__init__}.py + 8 子目录占位
│   ├── registry/{registry,__init__}.py + skills/marketplaces/capabilities/health 占位
│   ├── actions/gateway/{gateway,__init__}.py + policy/approval/idempotency/slippage/compensation 占位
│   ├── notifications/{dedup,__init__}.py
│   ├── domains/{travel,flight,hotel,railway,ecommerce,jobs,food} 占位
│   ├── adapters/{api,http,browser,mobile} 占位
│   ├── security/{credential_vault,session_broker,identity_vault,permissions} 占位
│   └── observability/{logs,traces,metrics,audit} 占位
└── tests/
    ├── conftest.py
    ├── contract/（5 个测试文件）
    ├── unit/（5 个测试文件）
    ├── integration/（2 个测试文件）
    ├── migration/test_host_swap.py
    ├── failure_injection/test_failure_injection.py
    └── replay/golden/policy/browser 占位
```
