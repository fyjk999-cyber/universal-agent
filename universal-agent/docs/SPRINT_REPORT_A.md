# SPRINT COMPLETED — SPRINT 0 (AUDIT) + SPRINT A (P0 Correctness Hardening)

> 日期：2026-08-14 · 测试基线 239 → **295 passed**

## 1. Problems fixed

| # | 问题 | 修复 |
|---|---|---|
| P0.1 | Scheduler 忽略 task timezone；due 用 `"09:00"<="21:00"` 字符串比较；无 misfire | BaselineScheduler 改用 IANA `ZoneInfo`（DST-safe）；`due_tasks_utc` datetime 比较；`MisfirePolicy`（SKIP/RUN_ONCE/CATCH_UP_LIMITED） |
| P0.2 | 平台临时失败 → Watch=FAILED 永久死亡 | `ScanRun` 独立状态（PENDING/RUNNING/SUCCESS/FAILED_RETRYABLE/FAILED_FATAL/PARTIAL/CANCELLED）；backoff 1m/5m/15m/1h；临时失败 Watch 保持 WATCHING |
| P0.3 | Slippage 自比较 `(confirmed, confirmed)` | `SlippageGuard(approved, actual)`；ActionIntent 增加 approved_* 快照；material change（行李/日期/币种）→ BLOCK |
| P0.4 | 成功路径调用 compensation | `TransactionExecutor` + `ExecutionState`；VERIFY SUCCESS → FINALIZE → NO COMPENSATION；仅 FAIL/UNKNOWN 补偿 |
| P0.5 | Idempotency 仅后置 register | `reserve→commit→finalize` 状态机 + `reconcile()`（commit 崩溃 → UNKNOWN → 查平台防双订单） |
| P0.6 | Skyscanner 硬编码 stops=0 获得直飞加分 | fail-closed：不完整数据 stops=-1；`DataCompleteness` + `field_completeness_score`；scoring 中性分 |
| P0.7 | 航班号缺失时同日期同路线错误合并 | strong/weak key + `ResolutionConfidence`（MATCH 才 merge；CONFLICT/PROBABLE_MATCH 不 merge） |
| P0.8 | 模糊断言掩盖逻辑错误；dedup 内存态 | 精确断言测试；`NotificationDedup` 持久化（restart-safe） |

## 2. Files changed

```
docs/CAPABILITY_MATRIX.md        (新增，能力审计)
docs/ROADMAP.md                  (新增)
docs/KNOWN_LIMITATIONS.md        (新增，P0 修复后更新)
core/contracts/scanrun.py        (新增：ScanRun/ScanRunStatus/ExecutionState/is_retryable)
core/contracts/action.py         (ActionIntent approved_* 字段)
core/contracts/raw.py            (DataCompleteness + field_completeness_score)
coordinator/scheduler/baseline.py (ZoneInfo + misfire)
coordinator/scheduler/daemon.py   (due_tasks_utc + ScanRun 分离)
coordinator/scheduler/__init__.py (导出 MisfirePolicy 等)
coordinator/task_registry/registry.py (due_tasks_utc)
coordinator/task_registry/scanruns.py (ScanRunRepository + 错误分类)
actions/slippage/guard.py        (approved/actual + material check)
actions/idempotency/store.py     (reserve/finalize/reconcile 状态机)
actions/compensation/manager.py  (保持不变，被正确调用)
actions/gateway/execute.py       (approved vs actual；成功不补偿；reserve/finalize)
actions/gateway/prepare.py       (记录批准快照；reserve/finalize)
actions/gateway/transaction.py   (新增：TransactionExecutor + ExecutionState)
actions/__init__.py / gateway/__init__.py (导出)
domains/flight/knowledge.py      (strong/weak key + resolve)
domains/flight/scoring.py        (fail-closed 中性分)
adapters/skyscanner/adapter.py   (completeness 标记 + stops=-1)
notifications/dedup.py           (持久化)
tests/unit/test_p0_*.py          (7 个测试文件，56 项)
```

## 3. Contracts changed

- `ActionIntent`：+approved_quote_id / approved_offer_id / approved_price_cny / approved_at / approval_expires_at / offer_version / candidate_version
- `ScanRun` + `ScanRunStatus` + `ExecutionState` + `is_retryable`（新契约）
- `DataCompleteness` + `field_completeness_score`（新契约）
- `MisfirePolicy` + `MissedRun` + `resolve_tz`（新）
- `ResolutionConfidence` + `ResolutionResult` + `resolve()`（新）

## 4. DB migrations

无（仍 JSON 持久化；SQLite 属 P1，未在本 Sprint 执行）。

## 5. Tests added

56 项（7 个文件）：
- test_p0_scheduler.py（8）：IANA 时区 / NY DST / invalid tz / due datetime / misfire RUN_ONCE/SKIP/CATCH_UP
- test_p0_scanrun.py（9）：ScanRun 状态 / backoff 递增 / 错误分类 / Watch 存活 / 致命标记
- test_p0_slippage.py（12）：approved=actual / 小涨幅 / 大涨幅 BLOCK / material change / 无快照 BLOCK
- test_p0_transaction.py（10）：成功不补偿 / execute 失败补偿 / verify 失败补偿 / IRREVERSIBLE / PARTIAL / 补偿失败审计 / reserve-commit-finalize / 崩溃 reconcile
- test_p0_failclosed.py（5）：不完整数据无直飞分 / 不完整不排顶 / completeness 标记 / score
- test_p0_entity.py（7）：strong key / CONFLICT / MATCH / weak PROBABLE_MATCH / weak vs strong 不 merge
- test_p0_hardening.py（4）：notification 重启存活 / 精确断言

## 6. Tests passed

**295 passed / 0 failed**（基线 239 + 56）

## 7. Regression status

- 全量回归通过；旧 API（`BaselineScheduler(tz=)` / `idempotency.register`）已同步更新
- Jarvis Host Swap + CareerPilot 迁移测试继续通过

## 8. Security impact

- Slippage 修复消除"确认价自比较"漏洞（防执行价暴涨）
- Compensation 成功路径修复消除"成功事务被错误回滚"
- Idempotency reconcile 防重复下单（commit 崩溃场景）
- 真实执行仍默认 DENY（§56/§66 边界保持）

## 9. Host coupling audit

CLEAN ✓（新增全在 core/coordinator/actions/domains/adapters，无 hosts 依赖；grep 验证）

## 10. Jarvis compatibility

- Host Swap Contract Test 通过（Core 零修改）
- 新增契约（ScanRun/ExecutionState）均为 Core 内部，不影响 Host 接口

## 11. Known limitations

- 持久化仍 JSON（SQLite 属 P1）
- NotificationDedup 持久化完成但缺 priority/channel（P11）
- ScanRunRepository 未接真实调度重试循环（backoff 已算，重试触发在 P1/P5）

## 12. Capability Matrix changes

见 `docs/CAPABILITY_MATRIX.md`：9 项 BROKEN/PARTIAL → IMPLEMENTED；新增 ScanRun/Transaction/DataCompleteness/EntityResolution 能力。

## 13. Next recommended sprint

**P1 — Single Source of Truth + SQLite**：
- Repository Protocol（Task/ScanRun/Event/Observation/Memory/Notification/Approval/Action/Audit）
- `data/universal_agent.db`（WAL）+ 表结构
- Task 真相单一化（消灭 Harness 双份）
- ScanRun 接真实重试循环
