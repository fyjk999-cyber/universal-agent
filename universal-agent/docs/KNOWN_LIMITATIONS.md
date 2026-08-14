# Known Limitations

> 更新：2026-08-14（SPRINT A / P0 完成后）· 基于实际代码审计

## ✅ P0 已修复（SPRINT A）

1. **Scheduler 时区**：BaselineScheduler 改用 IANA `ZoneInfo`（zoneinfo），DST-safe，`resolve_tz` 校验
2. **due 判定**：`due_tasks_utc` 用 datetime 比较（弃用字符串比较）
3. **Misfire**：`MisfirePolicy`（SKIP/RUN_ONCE/CATCH_UP_LIMITED），默认 RUN_ONCE 补跑
4. **Task/ScanRun 分离**：`ScanRunRepository` + `ScanRunStatus`；平台临时失败 → FAILED_RETRYABLE + backoff（1m/5m/15m/1h），Watch 保持 WATCHING
5. **Slippage**：approved vs actual 比较（弃自比较）；ActionIntent 增加 approved_* 快照；material change（行李/日期/币种）→ BLOCK
6. **Compensation**：成功路径绝不自动补偿；`TransactionExecutor` + `ExecutionState`；verify 失败才补偿
7. **Idempotency**：reserve/finalize/reconcile 状态机；commit 崩溃 → UNKNOWN → reconcile 查平台防双订单
8. **Skyscanner fail-closed**：不完整数据 stops=-1，禁止直飞/短时长加分；DataCompleteness + field_completeness_score
9. **Entity Resolution**：strong/weak key + ResolutionConfidence（MATCH 才合并；CONFLICT/PROBABLE_MATCH 不 merge）

## P1 — Persistence（后续）

- 全部 JSON 文件持久化（tasks/memory/observations/idempotency/approvals）
- HarnessHostAdapter 保存 Task 真相（与 TaskRegistry 双份）→ P1.1 消灭
- 无 Repository Protocol / SQLite

## P2 — 其它（后续）

- 8 个 Memory 子域（intent/preferences/decisions/answers/task_state/policy/execution_history）为空
- `security/` 全部空（无 CredentialVault）
- 无 Metrics/Traces/Logs 实现（仅 Audit）
- NotificationDedup 已持久化（P0.8）但缺 priority/channel 完整化（P11）
- 无 Transactional Outbox（事件可靠性仅进程内）
- SearchSpec 未强类型化（依赖 Dict[str,Any]）
- DSH Bridge 硬编码 `/Users/...` 路径（P4.1）

## 设计边界（非缺陷）

- 真实支付/自动执行默认 DENY（§56/§66）
- Tier3 官方源为骨架（NoOp/Stub）
- Railway/Ecommerce/Food 未实现（规划内）
