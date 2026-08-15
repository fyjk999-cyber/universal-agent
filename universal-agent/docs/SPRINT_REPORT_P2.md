# SPRINT COMPLETED — P2 (Reliable Events)

> 日期：2026-08-14 · 测试基线 401 → **409 passed**

## 1. Problems fixed

| # | 问题 | 修复 |
|---|---|---|
| P2.0 | 事件仅进程内（InProcessEventBus），无持久可靠投递 | SQLite EventStore（已有）+ **OutboxDispatcher**：pending→publish→delivered |
| P2.1 | 无重试/DLQ | Dispatcher 失败 → attempts 递增 → 达上限 DEAD（DLQ，可人工/补偿查询）；未达上限保留 PENDING 下轮重试 |
| P2.2 | EventEnvelope 缺 correlation_id/causation_id/run_id | 字段补全（指令 §P2 要求） |
| P2.3 | 业务状态与事件非同事务 | `Database.transaction()` 上下文（BEGIN/COMMIT/ROLLBACK）；业务状态+outbox 同事务原子写，回滚无孤儿 outbox |

## 2. Files changed

```
events/reliable.py                (新增：OutboxDispatcher)
events/envelope.py                (补 correlation_id/causation_id/run_id)
events/__init__.py                (导出 OutboxDispatcher)
persistence/sqlite.py             (新增 Database.transaction() 事务上下文)
persistence/protocol.py           (OutboxRepository 加 bump_attempts)
persistence/repos.py              (SqliteOutboxRepository.bump_attempts)
tests/unit/test_p2_reliable_events.py   (新增 5 项)
tests/integration/test_p2_outbox_pipeline.py (新增 3 项)
```

## 3. Tests added

8 项：
- 字段完整性（11 字段全在）
- Dispatcher 投递 + DELIVERED
- 重试后 DLQ（DEAD）
- outbox 跨重启保留
- 事务原子写（业务+outbox 同事务）
- 事务回滚无孤儿 outbox
- 全链路 outbox→events 表 + delivered
- trace_id 贯穿

## 4. Tests passed

**409 passed / 0 failed**（基线 401 + 8）

## 5. Known limitations

- Dispatcher 是拉模式（dispatch_once / run_forever），未接 daemon 后台循环（P5 接线）
- 无 Kafka/Redis（按计划通过 EventBusProtocol 保留替换）
- run_leases heartbeat 仍未接入（P3）

## 6. Next sprint

**P3 — Memory Completion**（8 子域真正实现：Intent/Preference/Decision/Observation/Answer/TaskState/Policy/ExecutionHistory + scope/expires_at）
