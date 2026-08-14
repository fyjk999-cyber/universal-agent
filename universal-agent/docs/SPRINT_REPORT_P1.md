# SPRINT COMPLETED — P1 (Single Source of Truth + SQLite)

> 日期：2026-08-14 · 测试基线 295 → **320 passed**

## 1. Problems fixed

| # | 问题 | 修复 |
|---|---|---|
| P1.0 | 全部 JSON 文件持久化，无正式本地存储 | SQLite + WAL（`data/universal_agent.db`），schema 版本化（user_version=1），19 张表 |
| P1.1 | 无 Repository 抽象，存储直接散落 | `Repository Protocol`：9 个抽象基类（Task/ScanRun/Event/Outbox/Observation/Memory/Notification/Approval/Action/Audit/SourceHealth） |
| P1.2 | HarnessHostAdapter 保存 Task 真相（双份） | `TaskCoordinator` 命令模式：Host 只发 Command（create/pause/resume/cancel），Task 状态只由 Coordinator → StateMachine → TaskRepository 修改 |
| P1.3 | ScanRun 无真实重试循环 | daemon `_retry_failed_runs()`：FAILED_RETRYABLE + backoff 到期 → 自动重试（attempt 递增） |
| P1.4 | Event/Observation/Memory 等无 DB 持久化 | 全部 SQLite Repository 实现（JSON 序列化到行） |
| P1.5 | Memory 仍 JSON | `SqliteMemoryStore`：scope 隔离 + expired 自动过滤 |

## 2. Files changed

```
persistence/__init__.py        (新增，导出)
persistence/sqlite.py          (新增：Database + WAL + schema)
persistence/protocol.py        (新增：Repository Protocol 9+ 基类)
persistence/task_repo.py       (新增：SqliteTaskRepository)
persistence/scanrun_repo.py    (新增：SqliteScanRunRepository)
persistence/repos.py           (新增：Event/Outbox/Observation/Memory/Notification/Approval/Action/Audit/SourceHealth)
coordinator/task_coordinator.py (新增：命令模式 + sqlite_task_coordinator 工厂)
coordinator/scheduler/daemon.py (新增 _retry_failed_runs 重试循环)
memory/sqlite_store.py         (新增：SqliteMemoryStore)
hosts/deepseek_harness/adapter.py (改造：只发 Command)
hosts/jarvis/adapter.py        (改造：只发 Command)
tests/unit/test_p1_persistence.py (新增 19 项)
tests/unit/test_p1_coordinator.py  (新增 4 项)
tests/unit/test_p1_retry.py        (新增 2 项)
tests/migration/test_host_swap.py  (更新：共享 SQLite 真相源)
tests/unit/test_adapter_state_machine.py (更新：Command 模式)
```

## 3. Contracts changed

无（Repository 层不改变契约；新增协议类）。

## 4. DB migrations

- `PRAGMA user_version=1` 版本化
- 19 张表：tasks/scan_runs/events/event_outbox/candidates/offers/quotes/observations/memories/preferences/decisions/answers/notifications/approvals/action_plans/action_intents/executions/audit_logs/source_health
- WAL 模式（并发读 + 单写）

## 5. Tests added

25 项（3 个新文件）：
- test_p1_persistence.py（19）：schema 19 表 / WAL / 重启存活 / Task 单真相 / ScanRun backoff / Event+Outbox / Observation / Memory / Notification / Approval / ActionPlan / Audit / SourceHealth / Memory 迁移 + expired 过滤
- test_p1_coordinator.py（4）：命令流 / Host 不存真相 / list/get
- test_p1_retry.py（2）：backoff 到期重试 / 已取消任务不重试

## 6. Tests passed

**320 passed / 0 failed**（基线 295 + 25）

## 7. Regression status

- 全量回归通过；Jarvis Host Swap（改造后共享 SQLite 真相）继续通过
- CareerPilot 迁移测试通过

## 8. Security impact

- Task 真相单一化：Host 不再能绕过状态机直接改 state（Command 模式）
- 状态转移全走 StateMachine 校验

## 9. Host coupling audit

CLEAN ✓（新增全在 persistence/coordinator/memory；hosts 仅依赖 coordinator 接口）

## 10. Jarvis compatibility

- Host Swap Contract Test 通过（Harness→Jarvis 共享同一 SQLite 真相源，Task/Memory 无缝迁移）
- 符合 P4.4：JarvisAdapter 同样 Command 模式

## 11. Known limitations

- Outbox 已建表但未接 Dispatcher（P3 完整）
- 事件/观察等 Repository 已实现，Shadow scan 尚未切换到 SQLite（P5 接线）
- 无 PostgreSQL（按计划第一阶段 SQLite）

## 12. Capability Matrix changes

persistence/sqlite: EMPTY → IMPLEMENTED；Task 双份真相: BROKEN → 单一真相源；ScanRun 重试: PARTIAL → IMPLEMENTED；Memory: JSON → SQLite（双后端）。

## 13. Next recommended sprint

**P2 — 完整 Memory System**（intent/preferences/decisions/answers/task_state/policy/execution_history 8 子域真正实现）
或 **P3 — Event Reliability**（Transactional Outbox Dispatcher 接入 Shadow scan）
