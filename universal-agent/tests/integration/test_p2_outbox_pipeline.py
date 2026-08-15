"""P2 集成 — Transactional Outbox 全链路 + 事务回滚原子性。"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from universal_agent.events.envelope import EventEnvelope
from universal_agent.events.types import EventType
from universal_agent.persistence import Database, SqliteEventRepository, SqliteOutboxRepository


def _evt(event_type=EventType.TASK_CREATED, task_id="t1") -> EventEnvelope:
    return EventEnvelope(event_type=event_type, trace_id="trc-1",
                         task_id=task_id, source="test")


def test_business_state_rollback_removes_outbox_row(tmp_path: Path) -> None:
    """事务中途失败 → 业务状态与 outbox 一起回滚（无孤儿 outbox）。"""
    db = Database(tmp_path / "ua.db")
    outbox = SqliteOutboxRepository(db)
    evt = _evt()
    try:
        with db.transaction() as conn:
            conn.execute(
                "INSERT INTO event_outbox (event_id, data, status, created_at) "
                "VALUES (?,?, 'PENDING', datetime('now'))",
                (evt.event_id, json.dumps(evt.model_dump(mode="json"), ensure_ascii=False)))
            raise RuntimeError("boom mid-transaction")
    except RuntimeError:
        pass
    # 事务回滚 → outbox 无残留
    assert outbox.pending() == []
    assert db.query_one("SELECT COUNT(*) AS n FROM event_outbox")["n"] == 0
    db.close()


def test_full_pipeline_outbox_to_eventstore(tmp_path: Path) -> None:
    """outbox → dispatcher → events 表（持久 EventStore）+ delivered。"""
    from universal_agent.events.reliable import OutboxDispatcher

    db = Database(tmp_path / "ua.db")
    outbox = SqliteOutboxRepository(db)
    events = SqliteEventRepository(db)
    seen: list = []

    async def handler(evt):
        seen.append(evt.event_type.value)

    disp = OutboxDispatcher(outbox=outbox, events=events,
                            handlers={EventType.TASK_CREATED: handler})
    e1 = _evt(EventType.TASK_CREATED)
    e2 = _evt(EventType.TASK_CREATED, task_id="t2")
    outbox.enqueue(e1)
    outbox.enqueue(e2)
    asyncio.run(disp.dispatch_once())

    assert sorted(seen) == [EventType.TASK_CREATED.value] * 2
    # events 表持久化
    stored = events.list_for(task_id=None, limit=10)
    assert len(stored) == 2
    # outbox 全部 delivered
    assert db.query_one("SELECT COUNT(*) AS n FROM event_outbox WHERE status='PENDING'")["n"] == 0
    db.close()


def test_trace_id_flows_through(tmp_path: Path) -> None:
    """trace_id 贯穿：outbox → handler。"""
    from universal_agent.events.reliable import OutboxDispatcher

    db = Database(tmp_path / "ua.db")
    outbox = SqliteOutboxRepository(db)
    seen = {}

    async def handler(evt):
        seen["trace"] = evt.trace_id

    disp = OutboxDispatcher(outbox=outbox, events=None,
                            handlers={EventType.SCAN_COMPLETED: handler})
    outbox.enqueue(EventEnvelope(event_type=EventType.SCAN_COMPLETED,
                                 trace_id="trace-xyz", task_id="t1", source="test"))
    asyncio.run(disp.dispatch_once())
    assert seen.get("trace") == "trace-xyz"
    db.close()
