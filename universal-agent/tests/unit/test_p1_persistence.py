"""P1 回归测试：SQLite + WAL + Repository Protocol + 单一真相源。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from universal_agent.core.contracts import (
    MemoryQuery,
    ScanRunStatus,
    Scope,
    WatchState,
    WatchTask,
)
from universal_agent.events import EventEnvelope, EventType
from universal_agent.persistence import (
    Database,
    SqliteActionRepository,
    SqliteApprovalRepository,
    SqliteAuditRepository,
    SqliteEventRepository,
    SqliteMemoryRepository,
    SqliteNotificationRepository,
    SqliteObservationRepository,
    SqliteOutboxRepository,
    SqliteScanRunRepository,
    SqliteSourceHealthRepository,
    SqliteTaskRepository,
)
from universal_agent.core.contracts import Observation, RawListing, RawLeg


def _task(task_id: str = "t1") -> WatchTask:
    return WatchTask(
        id=task_id, type="watch", domain="flight",
        schedule={"timezone": "Asia/Shanghai", "baseline": ["09:00"]},
        state=WatchState.WATCHING,
    )


@pytest.fixture
def db(tmp_path) -> Database:
    return Database(tmp_path / "ua.db")


class TestDatabaseInfra:
    def test_schema_initialized(self, db):
        tables = {r["name"] for r in db.query_all(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        for t in ("tasks", "scan_runs", "events", "event_outbox", "candidates",
                  "offers", "quotes", "observations", "memories", "preferences",
                  "decisions", "answers", "notifications", "approvals",
                  "action_plans", "action_intents", "executions", "audit_logs",
                  "source_health"):
            assert t in tables, f"missing table {t}"

    def test_wal_mode(self, db):
        row = db.query_one("PRAGMA journal_mode")
        assert row[0] == "wal"

    def test_restart_survives(self, tmp_path):
        path = tmp_path / "ua.db"
        d1 = Database(path)
        d1.execute("INSERT INTO tasks (id,data,state,updated_at) VALUES ('x','{}','DRAFT','t')")
        d1.close()
        d2 = Database(path)
        assert d2.query_one("SELECT id FROM tasks WHERE id='x'") is not None


class TestTaskRepository:
    def test_single_source_of_truth(self, db):
        """P1.2: Task 只存于 TaskRepository；Host 无独立真相。"""
        repo = SqliteTaskRepository(db)
        task = repo.create(_task())
        got = repo.get("t1")
        assert got is not None and got.id == "t1"
        assert [t.id for t in repo.list()] == ["t1"]

    def test_persistence_across_connection(self, tmp_path):
        path = tmp_path / "ua.db"
        d1 = Database(path)
        SqliteTaskRepository(d1).create(_task("persist"))
        d1.close()
        d2 = Database(path)
        assert SqliteTaskRepository(d2).get("persist") is not None

    def test_active_and_due(self, db):
        repo = SqliteTaskRepository(db)
        task = _task()
        task.next_scan_at = None
        from datetime import datetime, timedelta, timezone
        task.next_scan_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        repo.create(task)
        due = repo.due_tasks_utc(datetime.now(timezone.utc))
        assert "t1" in due
        assert len(repo.active_watches()) == 1


class TestScanRunRepository:
    def test_start_finish_retryable(self, db):
        repo = SqliteScanRunRepository(db)
        run = repo.start("t1")
        assert run.status == ScanRunStatus.RUNNING
        done = repo.finish(run.run_id, ScanRunStatus.FAILED_RETRYABLE,
                           error_type="source_unavailable")
        assert done.retry_count == 1
        assert done.next_retry_at is not None
        latest = repo.latest_for("t1")
        assert latest.run_id == run.run_id

    def test_retryable_sets_backoff(self, db):
        """backoff 已设置（1m），验证 retry_count 递增。"""
        repo = SqliteScanRunRepository(db)
        run = repo.start("t1")
        done = repo.finish(run.run_id, ScanRunStatus.FAILED_RETRYABLE,
                           error_type="source_unavailable")
        assert done.retry_count == 1
        assert done.next_retry_at is not None
        assert done.next_retry_at > done.finished_at


class TestEventOutbox:
    def test_event_append_and_list(self, db):
        repo = SqliteEventRepository(db)
        env = EventEnvelope(event_type=EventType.SCAN_REQUESTED, trace_id="tr",
                            task_id="t1")
        repo.append(env)
        events = repo.list_for("t1")
        assert len(events) == 1
        assert events[0].event_type == EventType.SCAN_REQUESTED

    def test_outbox_delivery(self, db):
        outbox = SqliteOutboxRepository(db)
        env = EventEnvelope(event_type=EventType.SCAN_REQUESTED, trace_id="tr2")
        oid = outbox.enqueue(env)
        pending = outbox.pending()
        assert len(pending) == 1
        assert pending[0]["outbox_id"] == oid
        outbox.mark_delivered(oid)
        assert outbox.pending() == []


class TestOtherRepos:
    def test_observation(self, db):
        repo = SqliteObservationRepository(db)
        obs = Observation(observation_id="o1", task_id="t1", domain="flight",
                          kind="price", value=4380, unit="CNY",
                          target_key="offer-1")
        repo.record(obs)
        assert repo.price_history("offer-1") == [4380.0]

    def test_memory(self, db):
        repo = SqliteMemoryRepository(db)
        repo.put(Scope.TASK, "pref", {"v": 1}, task_id="t1")
        got = repo.get(Scope.TASK, "pref", task_id="t1")
        assert got is not None and got.value == {"v": 1}
        q = MemoryQuery(scope=Scope.TASK, task_id="t1")
        assert len(repo.query(q)) == 1

    def test_notification(self, db):
        repo = SqliteNotificationRepository(db)
        repo.record("fp1", "t1", {"sent_at": "2026-08-14"})
        assert repo.get("fp1")["sent_at"] == "2026-08-14"

    def test_approval(self, db):
        repo = SqliteApprovalRepository(db)
        a = repo.request({"approval_id": "ap1", "status": "PENDING", "title": "buy"})
        assert len(repo.pending()) == 1
        repo.update("ap1", status="APPROVED")
        assert repo.find("ap1")["status"] == "APPROVED"

    def test_action_plan(self, db):
        from universal_agent.core.contracts import ActionIntent, ActionPlan, ActionLevel
        intent = ActionIntent(intent_id="i1", action="prepare_order",
                              idempotency_key="k1", level=ActionLevel.L2_PREPARE)
        plan = ActionPlan(plan_id="p1", task_id="t1", intents=[intent])
        repo = SqliteActionRepository(db)
        repo.save_plan(plan)
        repo.save_execution({"run_id": "e1", "intent_id": "i1", "task_id": "t1"})
        assert len(repo.list_executions("t1")) == 1

    def test_audit(self, db):
        repo = SqliteAuditRepository(db)
        repo.record({"ts": "2026-08-14T00:00:00Z", "action": "TEST", "actor": "u"})
        entries = repo.entries()
        assert len(entries) == 1
        assert entries[0]["actor"] == "u"

    def test_source_health(self, db):
        repo = SqliteSourceHealthRepository(db)
        repo.set("ctrip", {"status": "HEALTHY", "success_rate": 0.9})
        assert repo.get("ctrip")["status"] == "HEALTHY"


class TestSqliteMemoryMigration:
    def test_put_get_expired_filtered(self, db):
        from universal_agent.memory.sqlite_store import SqliteMemoryStore
        from datetime import datetime, timedelta, timezone
        store = SqliteMemoryStore(db)
        rec = store.put(Scope.GLOBAL, "k", {"v": 1})
        assert store.get(Scope.GLOBAL, "k").value == {"v": 1}
        # 设置过期 → 自动过滤
        rec.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        store._save(rec)
        assert store.get(Scope.GLOBAL, "k") is None

    def test_scope_isolation_sqlite(self, db):
        from universal_agent.memory.sqlite_store import SqliteMemoryStore
        store = SqliteMemoryStore(db)
        store.put(Scope.TASK, "k", 1, task_id="t1")
        store.put(Scope.GLOBAL, "k", 2)
        assert store.get(Scope.TASK, "k", task_id="t1").value == 1
        assert store.get(Scope.GLOBAL, "k").value == 2
