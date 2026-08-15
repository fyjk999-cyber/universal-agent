# SPRINT COMPLETED — P1.1 (Runtime Unification)

> 日期：2026-08-14 · 测试基线 376 → **401 passed**

## 1. Problems fixed

| # | 问题 | 修复 |
|---|---|---|
| P1.1a | 防双运行只有进程内 `RunningTaskGuard` | **RunLease**（DB-backed）：`run_leases` 表 + acquire/renew/release/recover_expired，多进程/Harness/Scheduler/未来 Jarvis 共享同一 DB 时天然互斥 |
| P1.1b | WatchDaemon 仍创建 JSON TaskRegistry / JSON ScanRunRepository | `load_watch_daemon` 改用 **SqliteTaskRepository + SqliteScanRunRepository**（Repository Protocol 注入）；JSON dual state 消除 |
| P1.1c | HarnessHostAdapter.update_task 直接 `coordinator.repo.update()`（Host 有 Repository 写权限） | 新增 **TaskCoordinator.apply_update()** 命令（StateMachine 校验转移），Harness + Jarvis 两个 adapter 都改为经命令；非法转移抛 TransitionError |
| P1.1d | 无统一装配入口 | 新增 **UniversalAgentService**（唯一 Repository Set + Coordinator + Adapter）；WatchDaemon 三路径（baseline/retry/misfire）接入 RunLease |
| P1.1e | Transaction external-call 歧义 | 验证并锁定：external 异常 → **UNKNOWN**（非 FAILED_SAFE_TO_RETRY）→ reconcile（CONFIRMED→FINALIZED / NOT_FOUND→SAFE_TO_RETRY / UNKNOWN→HUMAN） |

## 2. Files changed

```
persistence/sqlite.py            (SCHEMA_VERSION 1→2，新增 run_leases 表)
coordinator/scheduler/runlease.py (新增：RunLease DB-backed 租约)
coordinator/scheduler/daemon.py   (Repository 注入 + lease 三路径接入)
coordinator/task_coordinator.py   (新增 apply_update 命令)
hosts/deepseek_harness/adapter.py (update_task → apply_update 命令)
hosts/jarvis/adapter.py           (同上)
service.py                        (新增：UniversalAgentService 统一装配)
tests/unit/test_p11_runlease.py       (新增 8 项)
tests/unit/test_p11_runtime_unify.py  (新增 4 项)
tests/unit/test_p11_host_boundary.py  (新增 3 项)
tests/unit/test_p11_service_lease.py  (新增 3 项)
tests/unit/test_p11_tx_ambiguity.py   (新增 4 项)
tests/integration/test_p11_acceptance.py (新增 3 项)
tests/unit/test_scheduler_daemon.py    (修复时间敏感测试)
```

## 3. Contracts changed

无（Repository 层不改变契约；新增 RunLease 与 apply_update 命令，均为新增能力）。

## 4. DB migrations

- `PRAGMA user_version` 1 → **2**
- 新增 `run_leases` 表：task_id(PK) / lease_owner / lease_token / acquired_at / heartbeat_at / lease_expires_at

## 5. Tests added

25 项（6 个新文件 + 1 个修复）：
- RunLease 8：acquire/互斥/release/renew/过期恢复/跨实例/并发/元数据
- Runtime Unify 4：无 JSON dual state / SQLite 任务 / 重启保留 / Host 同源
- Host Boundary 3：非法转移拒绝 / 无直接 repo 写 / 无 Coordinator 时 fail-closed
- Service+Lease 3：服务聚合 / 双 daemon 防双运行 / 运行后释放 lease
- Tx Ambiguity 4：external 异常→UNKNOWN / reconcile CONFIRMED/NOT_FOUND/UNKNOWN
- Acceptance 3：双实例共享状态 / 双 daemon 单次执行 / 重启保留 Task+ScanRun

## 6. Tests passed

**401 passed / 0 failed**（基线 376 + 25）。另修复 3 个既有时间敏感测试（`now.replace(hour=9)` → 过去时间，避免 UTC 早于 9:00 时误判未来）。

## 7. Regression status

- 全量回归通过（401）
- Jarvis Host Swap（test_host_swap）继续通过：Host 也经 apply_update 命令
- P0 transaction / idempotency / daemon retry 全部回归通过

## 8. Security impact

- **Host 无 Repository 写权限**：唯一入口是 TaskCoordinator 命令（StateMachine 校验状态转移）
- 非法状态转移（DRAFT→FAILED 等）被拒绝，不再能绕过状态机直接改 state
- RunLease token 校验：release/renew 须 token 匹配，防误释放他人租约

## 9. Host coupling audit

CLEAN ✓：新增全在 persistence/coordinator/service；hosts 仅依赖 Coordinator 接口；`UniversalAgentService` 是唯一装配点，Host 替换（Harness→Jarvis）只换 adapter 构造参数。

## 10. Jarvis compatibility

- `UniversalAgentService(host="jarvis")` 一键换 Host；Core 零修改
- MockJarvisHostAdapter 同样走 apply_update 命令
- Host Swap Contract Test 通过

## 11. Known limitations

- RunLease 未接入 heartbeat 后台线程（renew 由调用方负责；当前单次执行场景足够）
- UniversalAgentService 的 RepositorySet 目前含 tasks/scan_runs；memory/events/observations 等在 P3 并入
- 无 PostgreSQL（按计划第一阶段 SQLite）

## 12. Capability Matrix changes

- RunLease（DB 防双运行）: EMPTY → IMPLEMENTED
- WatchDaemon Runtime Truth: JSON dual state → SQLite 唯一真相
- Host Write Boundary: BROKEN（直接 repo.update）→ IMPLEMENTED（命令模式）
- UniversalAgentService: EMPTY → IMPLEMENTED

## 13. Next recommended sprint

**P2 — Reliable Events**（SQLite EventStore + Transactional Outbox + Dispatcher + Retry + DLQ）
或 **P3 — Memory Completion**（8 子域真正实现）

## P1.1 Acceptance 对照

| 验收点 | 状态 | 证据 |
|---|---|---|
| 重启不丢 Task | ✅ | test_restart_preserves_scanrun_and_task / test_restart_preserves_task_in_sqlite |
| Host/Daemon 看到同一 Task State | ✅ | test_daemon_and_host_share_repository_set / test_two_service_instances_share_task_state |
| 无 JSON dual truth | ✅ | test_no_json_dual_state（data/ 无 task_registry.json / scan_runs 目录） |
| 多进程 lease 防双运行 | ✅ | test_two_daemons_same_task_runs_once / test_lease_prevents_concurrent_execution |
| external timeout 不造成二次执行 | ✅ | test_external_timeout_is_unknown_not_failed / test_reconcile_confirmed_prevents_duplicate |
