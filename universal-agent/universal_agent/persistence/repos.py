"""其余 SQLite Repository 实现（P1.4）.

Event / Outbox / Observation / Memory / Notification / Approval / Action /
Audit / SourceHealth。全部 JSON 序列化到 SQLite 行（契约对象 ↔ DB 行）。
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from ..core.contracts import MemoryQuery, MemoryRecord, Observation, Scope
from .protocol import (
    ActionRepository,
    ApprovalRepository,
    AuditRepository,
    EventRepository,
    MemoryRepository,
    NotificationRepository,
    ObservationRepository,
    OutboxRepository,
    SourceHealthRepository,
)
from .sqlite import Database


def _j(obj) -> str:
    if hasattr(obj, "model_dump"):
        return json.dumps(obj.model_dump(mode="json"), ensure_ascii=False)
    return json.dumps(obj, ensure_ascii=False, default=str)


class SqliteEventRepository(EventRepository):
    def __init__(self, db: Database) -> None:
        self.db = db

    def append(self, event: Any) -> None:
        self.db.execute("INSERT OR REPLACE INTO events (event_id, event_type, data) "
                        "VALUES (?,?,?)",
                        (event.event_id, event.event_type.value, _j(event)))

    def list_for(self, task_id: Optional[str] = None, limit: int = 100) -> List[Any]:
        from ..events import EventEnvelope
        if task_id:
            rows = self.db.query_all(
                "SELECT data FROM events WHERE json_extract(data,'$.task_id')=? "
                "ORDER BY rowid DESC LIMIT ?", (task_id, limit))
        else:
            rows = self.db.query_all("SELECT data FROM events ORDER BY rowid "
                                     "DESC LIMIT ?", (limit,))
        out = []
        for r in rows:
            try:
                out.append(EventEnvelope.model_validate(json.loads(r["data"])))
            except Exception:  # noqa: BLE001
                continue
        return out


class SqliteOutboxRepository(OutboxRepository):
    def __init__(self, db: Database) -> None:
        self.db = db

    def enqueue(self, event: Any) -> int:
        cur = self.db.execute(
            "INSERT INTO event_outbox (event_id, data, status, created_at) "
            "VALUES (?,?, 'PENDING', datetime('now'))",
            (event.event_id, _j(event)))
        return cur.lastrowid

    def pending(self, limit: int = 100) -> List[Dict[str, Any]]:
        rows = self.db.query_all(
            "SELECT outbox_id, event_id, data, status, attempts FROM event_outbox "
            "WHERE status='PENDING' ORDER BY outbox_id LIMIT ?", (limit,))
        return [dict(r) for r in rows]

    def mark_delivered(self, outbox_id: int) -> None:
        self.db.execute("UPDATE event_outbox SET status='DELIVERED' WHERE outbox_id=?",
                        (outbox_id,))

    def mark_dead(self, outbox_id: int, error: str) -> None:
        self.db.execute("UPDATE event_outbox SET status='DEAD', attempts=attempts+1 "
                        "WHERE outbox_id=?", (outbox_id,))

    def bump_attempts(self, outbox_id: int, attempts: int) -> None:
        self.db.execute("UPDATE event_outbox SET attempts=? WHERE outbox_id=?",
                        (attempts, outbox_id))


class SqliteObservationRepository(ObservationRepository):
    def __init__(self, db: Database) -> None:
        self.db = db

    def record(self, observation: Observation) -> Observation:
        self.db.execute(
            "INSERT OR REPLACE INTO observations (observation_id, task_id, kind, data) "
            "VALUES (?,?,?,?)",
            (observation.observation_id, observation.task_id,
             observation.kind, _j(observation)))
        return observation

    def price_history(self, target_key: str) -> List[float]:
        rows = self.db.query_all(
            "SELECT data FROM observations WHERE kind='price' "
            "AND json_extract(data,'$.target_key')=?", (target_key,))
        return [float(json.loads(r["data"])["value"]) for r in rows]

    def list_all(self) -> List[Observation]:
        rows = self.db.query_all("SELECT data FROM observations")
        return [Observation.model_validate(json.loads(r["data"])) for r in rows]


class SqliteMemoryRepository(MemoryRepository):
    def __init__(self, db: Database) -> None:
        self.db = db

    def put(self, scope: Scope, key: str, value, **kw) -> MemoryRecord:
        rec = MemoryRecord(
            record_id=kw.get("record_id", f"mem_{abs(hash(key))%10**8}"),
            scope=scope, domain=kw.get("domain"), task_id=kw.get("task_id"),
            key=key, value=value, kind=kw.get("kind", "fact"),
            source=kw.get("source", "system"))
        self.db.execute(
            "INSERT OR REPLACE INTO memories (record_id, scope, key, task_id, data) "
            "VALUES (?,?,?,?,?)",
            (rec.record_id, rec.scope.value, rec.key, rec.task_id, _j(rec)))
        return rec

    def get(self, scope: Scope, key: str, **kw) -> Optional[MemoryRecord]:
        rows = self.db.query_all(
            "SELECT data FROM memories WHERE scope=? AND key=? "
            "AND (task_id IS ? OR task_id=? OR ? IS NULL)",
            (scope.value, key, kw.get("task_id"), kw.get("task_id"),
             kw.get("task_id")))
        if not rows:
            return None
        return MemoryRecord.model_validate(json.loads(rows[0]["data"]))

    def query(self, q: MemoryQuery) -> List[MemoryRecord]:
        from ..core.contracts import utc_now
        rows = self.db.query_all("SELECT data FROM memories")
        out = []
        now = utc_now()
        for r in rows:
            rec = MemoryRecord.model_validate(json.loads(r["data"]))
            # P1.5: expired 自动过滤
            if rec.expires_at is not None and rec.expires_at <= now:
                continue
            if q.scope is not None and rec.scope != q.scope:
                continue
            if q.domain is not None and rec.domain != q.domain:
                continue
            if q.task_id is not None and rec.task_id != q.task_id:
                continue
            if q.key is not None and rec.key != q.key:
                continue
            if q.kind is not None and rec.kind != q.kind:
                continue
            out.append(rec)
        return out[: q.limit]


class SqliteNotificationRepository(NotificationRepository):
    def __init__(self, db: Database) -> None:
        self.db = db

    def record(self, fingerprint: str, task_id: str, state: Dict[str, Any]) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO notifications (fingerprint, task_id, data) "
            "VALUES (?,?,?)", (fingerprint, task_id, json.dumps(state)))

    def get(self, fingerprint: str) -> Optional[Dict[str, Any]]:
        row = self.db.query_one("SELECT data FROM notifications WHERE fingerprint=?",
                                (fingerprint,))
        return json.loads(row["data"]) if row else None


class SqliteApprovalRepository(ApprovalRepository):
    def __init__(self, db: Database) -> None:
        self.db = db

    def request(self, approval: Dict[str, Any]) -> Dict[str, Any]:
        self.db.execute(
            "INSERT OR REPLACE INTO approvals (approval_id, status, data) "
            "VALUES (?,?,?)",
            (approval["approval_id"], approval.get("status", "PENDING"),
             json.dumps(approval, ensure_ascii=False)))
        return approval

    def update(self, approval_id: str, **kw) -> Dict[str, Any]:
        approval = self.find(approval_id)
        if approval is None:
            raise KeyError(f"approval not found: {approval_id}")
        approval.update(kw)
        return self.request(approval)

    def find(self, approval_id: str) -> Optional[Dict[str, Any]]:
        row = self.db.query_one("SELECT data FROM approvals WHERE approval_id=?",
                                (approval_id,))
        return json.loads(row["data"]) if row else None

    def pending(self) -> List[Dict[str, Any]]:
        rows = self.db.query_all("SELECT data FROM approvals WHERE status='PENDING'")
        return [json.loads(r["data"]) for r in rows]


class SqliteActionRepository(ActionRepository):
    def __init__(self, db: Database) -> None:
        self.db = db

    def save_plan(self, plan: Any) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO action_plans (plan_id, task_id, data) "
            "VALUES (?,?,?)",
            (plan.plan_id, plan.task_id, _j(plan)))
        for intent in plan.intents:
            self.db.execute(
                "INSERT OR REPLACE INTO action_intents (intent_id, plan_id, data) "
                "VALUES (?,?,?)", (intent.intent_id, plan.plan_id, _j(intent)))

    def save_execution(self, execution: Dict[str, Any]) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO executions (run_id, intent_id, data) "
            "VALUES (?,?,?)",
            (execution.get("run_id"), execution.get("intent_id"),
             json.dumps(execution, ensure_ascii=False)))

    def list_executions(self, task_id: Optional[str] = None) -> List[Dict[str, Any]]:
        if task_id:
            rows = self.db.query_all(
                "SELECT data FROM executions WHERE json_extract(data,'$.task_id')=?",
                (task_id,))
        else:
            rows = self.db.query_all("SELECT data FROM executions")
        return [json.loads(r["data"]) for r in rows]


class SqliteAuditRepository(AuditRepository):
    def __init__(self, db: Database) -> None:
        self.db = db

    def record(self, entry: Dict[str, Any]) -> None:
        self.db.execute("INSERT INTO audit_logs (ts, action, data) VALUES (?,?,?)",
                        (entry.get("ts", ""), entry.get("action", ""),
                         json.dumps(entry, ensure_ascii=False)))

    def entries(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        if limit:
            rows = self.db.query_all("SELECT data FROM audit_logs ORDER BY seq DESC "
                                     "LIMIT ?", (limit,))
        else:
            rows = self.db.query_all("SELECT data FROM audit_logs ORDER BY seq")
        return [json.loads(r["data"]) for r in rows]


class SqliteSourceHealthRepository(SourceHealthRepository):
    def __init__(self, db: Database) -> None:
        self.db = db

    def set(self, marketplace_id: str, health: Dict[str, Any]) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO source_health (marketplace_id, data) "
            "VALUES (?,?)", (marketplace_id, json.dumps(health, ensure_ascii=False)))

    def get(self, marketplace_id: str) -> Optional[Dict[str, Any]]:
        row = self.db.query_one("SELECT data FROM source_health WHERE marketplace_id=?",
                                (marketplace_id,))
        return json.loads(row["data"]) if row else None

    def list(self) -> List[Dict[str, Any]]:
        rows = self.db.query_all("SELECT data FROM source_health")
        return [json.loads(r["data"]) for r in rows]


class SqliteKvRepository:
    """P23（RULE-003）：通用 key-value SQLite 仓库。

    用于 idempotency / notification_dedup / killswitch 状态（表名取自有界集合）。
    API：get(key) / put(key, value) / list_all()。
    """

    _TABLES = ("idempotency", "notification_dedup", "killswitch")

    def __init__(self, db: Database, table: str) -> None:
        if table not in self._TABLES:
            raise ValueError(f"unsupported kv table: {table}")
        self.db = db
        self.table = table

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        row = self.db.query_one(
            f"SELECT data FROM {self.table} WHERE key=?", (key,))
        return json.loads(row["data"]) if row else None

    def put(self, key: str, value: Dict[str, Any]) -> None:
        self.db.execute(
            f"INSERT OR REPLACE INTO {self.table} (key, data) VALUES (?,?)",
            (key, json.dumps(value, ensure_ascii=False)))

    def list_all(self) -> List[Dict[str, Any]]:
        rows = self.db.query_all(f"SELECT data FROM {self.table}")
        return [json.loads(r["data"]) for r in rows]
