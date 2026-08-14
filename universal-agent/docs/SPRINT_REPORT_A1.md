# SPRINT A.1 COMPLETED — P0.9 Correctness Closure

> 日期：2026-08-14 · 测试基线 320 → **376 passed**（+56）

## 1. Root causes

| # | 根因 | 修复 |
|---|---|---|
| P0.9-1 | retry 不真正由 next_retry_at 驱动；失败后 next_scan_at 保持过期 → 每 tick 重复触发；无防双启动 | RunGuard + 失败推进 next_scan_at + retry chain 跨重启 |
| P0.9-2 | `_has_complete_segments` 空列表 for 不执行直接 True | round-trip 双方向非空 + 全字段校验 |
| P0.9-3 | `duration > 0` 误判 STRUCTURED；未知 stops 写 0 | duration-only 恒 PARTIAL；stops 未知 = -1 |
| P0.9-4 | PARTIAL 仍可进 Final Top5 | RankEligibility Gate（PRELIMINARY 分离） |
| P0.9-5 | idempotency RESERVED/COMMITTED/UNKNOWN 残留直接执行；双 L3/L4 路径 | reconcile 拦截 + ControlledExecutor 改 wrapper |
| P0.9-6 | 审批过期/offer/quote/材料变化未检查 | Approval Snapshot 校验（REAPPROVAL_REQUIRED） |
| P0.9-7 | `due_tasks(now_str)` 字符串比较仍在 | 删除，生产路径全用 due_tasks_utc |

## 2. Files changed

```
core/contracts/scanrun.py        (+retry_of_run_id/parent_run_id)
core/contracts/raw.py            (+RankEligibility/rank_eligibility/_structurally_complete)
coordinator/scheduler/runguard.py(新增：RunningTaskGuard)
coordinator/scheduler/daemon.py  (RunGuard + retry 驱动 + 失败推进 next_scan_at + 防双启动)
coordinator/scheduler/__init__.py
coordinator/task_registry/scanruns.py (start_retry + retry chain)
coordinator/task_registry/registry.py (删除 due_tasks(string))
coordinator/watch_manager/manager.py (due_tasks_utc)
adapters/skyscanner/adapter.py  (恒 PARTIAL + stops=-1)
actions/gateway/transaction.py  (reconcile + approval snapshot + Commit Boundary)
actions/gateway/execute.py      (ControlledExecutor → wrapper)
actions/idempotency/store.py    (unresolved 含 COMMITTED)
tests/unit/test_p09_{retry,entity,completeness,eligibility,idempotency,approval,deprecated}.py (新增 7 文件)
tests/integration/test_p09_{runtime,flight_pipeline,transaction_crash}.py (新增 3 文件)
```

## 3. Contracts changed

- `ScanRun`: +`retry_of_run_id` / `parent_run_id`（retry chain 跨重启）
- `RankEligibility` + `rank_eligibility()`（新契约）
- `DataCompleteness` 语义修正：duration-only 恒 PARTIAL

## 4. Retry architecture

```
WatchTask
 ├─ Baseline Schedule → next_scan_at（成功/失败都推进）
 └─ Retry Schedule    → next_retry_at（FAILED_RETRYABLE 时）
        │ backoff: 1m/5m/15m/1h（跨重启经 retry_of_run_id 继承）
        ▼ 到期 → start_retry()（attempt+1, retry_count+1）→ 执行
        ├─ 成功 → SUCCESS → 恢复 baseline
        └─ 失败 → 再 FAILED_RETRYABLE → 继续 backoff
RunGuard: 同一 task 同时只一个 RUNNING ScanRun（防 baseline+retry 双启动）
```

## 5. Ranking eligibility architecture

```
Raw Pool → rank_eligibility()
  DISCOVERED → DISCOVERY_ONLY（不进排行）
  PARTIAL    → PRELIMINARY（preliminary_top 展示，不触发购买）
  STRUCTURED → FINAL_ELIGIBLE（Final Top5）
  VERIFIED   → ACTION_ELIGIBLE（可 prepare）
```

## 6. Idempotency / reconciliation architecture

```
NEW → RESERVED → COMMITTING → COMMITTED → VERIFYING → FINALIZED
  crash 于 COMMITTING/COMMITTED → UNKNOWN
  UNKNOWN → reconcile()
    CONFIRMED → FINALIZED（防重复执行）
    NOT_FOUND → SAFE_TO_RETRY
    UNKNOWN   → RECONCILE_UNKNOWN（人工）
```

## 7. Executor consolidation result

- L3/L4 唯一正式路径：**TransactionExecutor**
- `ControlledExecutor` = deprecated wrapper（KillSwitch→Policy→Slippage→Approval→委托）

## 8. Tests added

56 项（7 unit + 3 integration）：
- retry(10)：backoff 时序 / 防双启动 / RunGuard / 跨重启 / 恢复 baseline
- entity(7)：空/单程/缺字段绝不 Strong
- completeness(5)：duration-only PARTIAL / stops=-1
- eligibility(8)：PARTIAL 不进 Final Top5 / 不触发购买 / 最便宜 PARTIAL 不敌 STRUCTURED
- idempotency(8)：RESERVED/COMMITTED/UNKNOWN 需 reconcile / CONFIRMED 防双执行
- approval(8)：expiry/offer/quote/baggage/room/passenger 变化需重审
- deprecated(4)：生产路径无字符串比较
- integration(6)：runtime 闭环 / flight gate 流程 / crash reconcile

## 9. Total tests passed

**376 passed / 0 failed**

## 10. Regression status

- 全量回归通过；无 xfail/skip/放宽断言
- Jarvis Host Swap + CareerPilot 迁移测试继续通过（14 passed）

## 11. Security impact

- 崩溃后绝不二次执行（reconcile CONFIRMED → FINALIZED）
- 审批过期/材料变化强制重新审批
- PARTIAL 数据不产生购买建议/不进 ActionPlan
- 单一 L3/L4 执行路径消除双实现安全缺口

## 12. Host coupling audit

CLEAN ✓（Core 无 Harness 依赖，grep 验证）

## 13. Jarvis compatibility

Host Swap Contract Test 通过（Core 零修改）

## 14. Remaining known limitations

- Outbox Dispatcher 未接入（P3）
- 事件/观察等 SQLite Repository 已实现但 shadow scan 未切换（P5 接线）
- Preference Learning / Adaptive Scheduler / 真实购票：按计划禁止

## 15. P1 readiness recommendation

**READY**。P0 correctness 已闭环（376 测试绿），可进入 P1 — SQLite + Single Source of Truth + Repository Protocol。

---

**ACCEPTANCE CRITERIA 全部达成**：retry 由 next_retry_at 驱动 / backoff 跨重启 / empty segments 不 Strong / duration-only PARTIAL / PARTIAL 不进 Final Top5 不产生购买建议不进 ActionPlan / RESERVED/COMMITTED/UNKNOWN 需 reconcile / crash 不二次执行 / approval expiry 生效 / material change 重审 / L3/L4 单一路径 / Watch 源失败存活 / 0 failed / Core 无 Harness 依赖 / Jarvis Swap 通过。

**STOP — 等待人工代码审核。**
