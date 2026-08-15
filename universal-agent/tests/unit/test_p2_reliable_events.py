"""P2 — Reliable Events：SQLite EventStore + Outbox Dispatcher + Retry + DLQ。

验收：
1. EventEnvelope 含 schema_version/event_id/event_type/trace_id/correlation_id/
   causation_id/task_id/run_id/source/created_at/payload
2. Dispatcher 从 outbox 取 pending → publish → mark delivered
3. 发送失败 → attempts 递增，超过上限 → DLQ（DEAD）
4. 事务性：业务状态 + outbox 同写（同一事务原子性）
5. 跨重启：outbox 中未投递事件保留
"""
from __future__ import annotations

from pathlib import Path

import pytest

from universal_agent.events.envelope import EventEnvelope
from universal_agent.events.types import EventType


def _evt(**kw) -> EventEnvelope:
    base = dict(
        event_type=EventType.TASK_CREATED, trace_id="trc-1",
        task_id="t1", source="test",
    )
    base.update(kw)
    return EventEnvelope(**base)


def test_envelope_has_required_fields() -> None:
    """指令要求的完整字段集。"""
    e = _evt()
    for field in ("schema_version", "event_id", "event_type", "trace_id",
                  "correlation_id", "causation_id", "task_id", "run_id",
                  "source", "created_at", "payload"):
        assert hasattr(e, field), f"missing field: {field}"


def test_dispatcher_delivers_and_marks_delivered(tmp_path: Path) -> None:
    from universal_agent.events.reliable import OutboxDispatcher
    from universal_agent.persistence import Database, SqliteEventRepository, SqliteOutboxRepository

    db = Database(tmp_path / "ua.db")
    outbox = SqliteOutboxRepository(db)
    events = SqliteEventRepository(db)
    dispatched: list = []

    async def handler(evt):
        dispatched.append(evt.event_type)

    disp = OutboxDispatcher(outbox=outbox, events=events,
                            handlers={EventType.TASK_CREATED: handler})
    oid = outbox.enqueue(_evt())
    import asyncio
    asyncio.run(disp.dispatch_once())
    assert len(dispatched) == 1
    row = db.query_one("SELECT status FROM event_outbox WHERE outbox_id=?", (oid,))
    assert row["status"] == "DELIVERED"
    db.close()


def test_dispatcher_retries_then_dlq(tmp_path: Path) -> None:
    from universal_agent.events.reliable import OutboxDispatcher
    from universal_agent.persistence import Database, SqliteOutboxRepository

    db = Database(tmp_path / "ua.db")
    outbox = SqliteOutboxRepository(db)
    calls = {"n": 0}

    async def flaky(evt):
        calls["n"] += 1
        raise RuntimeError("handler boom")

    disp = OutboxDispatcher(outbox=outbox, events=None,
                            handlers={EventType.TASK_CREATED: flaky},
                            max_attempts=2)
    oid = outbox.enqueue(_evt())
    import asyncio
    asyncio.run(disp.dispatch_once())
    asyncio.run(disp.dispatch_once())
    # 达到最大尝试次数 → DEAD（DLQ）
    row = db.query_one("SELECT status, attempts FROM event_outbox WHERE outbox_id=?", (oid,))
    assert row["status"] == "DEAD"
    assert calls["n"] >= 2
    db.close()


def test_outbox_survives_restart(tmp_path: Path) -> None:
    """未投递事件跨重启保留。"""
    from universal_agent.persistence import Database, SqliteOutboxRepository

    db1 = Database(tmp_path / "ua.db")
    outbox1 = SqliteOutboxRepository(db1)
    outbox1.enqueue(_evt())
    db1.close()

    # 重启
    db2 = Database(tmp_path / "ua.db")
    outbox2 = SqliteOutboxRepository(db2)
    pending = outbox2.pending()
    assert len(pending) == 1
    db2.close()


def test_transactional_append_business_and_outbox(tmp_path: Path) -> None:
    """业务状态 + outbox 在同一事务（原子）。"""
    from universal_agent.persistence import Database, SqliteOutboxRepository, SqliteTaskRepository
    from universal_agent.core.contracts import WatchTask, WatchState

    db = Database(tmp_path / "ua.db")
    tasks = SqliteTaskRepository(db)
    outbox = SqliteOutboxRepository(db)
    task = WatchTask(
        id="t1", type="watch", domain="flight",
        schedule={"timezone": "Asia/Shanghai", "baseline": ["09:00"]},
        state=WatchState.DRAFT,
    )
    evt = _evt(event_type=EventType.TASK_CREATED, task_id="t1")

    with db.transaction() as conn:
        # 同事务：写 task + enqueue outbox
        conn.execute(
            "INSERT OR REPLACE INTO tasks (id, data, state, next_scan_at, updated_at) "
            "VALUES (?,?,?,?,?)",
            ("t1", '{"id":"t1"}', "DRAFT", None, "2026-08-14T00:00:00+00:00"))
        import json
        conn.execute(
            "INSERT INTO event_outbox (event_id, data, status, created_at) "
            "VALUES (?,?, 'PENDING', datetime('now'))",
            (evt.event_id, json.dumps(evt.model_dump(mode="json"), ensure_ascii=False)))

    row = db.query_one("SELECT data FROM tasks WHERE id=?", ("t1",))
    assert row is not None
    pending = outbox.pending()
    assert len(pending) == 1
    db.close()
