"""SQLite + WAL 持久化基础设施（P1）.

- data/universal_agent.db（WAL 模式，concurrent read + single write）
- Schema 版本化迁移（PRAGMA user_version）
- 表结构按 P1 需求：tasks / scan_runs / events / event_outbox / candidates /
  offers / quotes / observations / memories / preferences / decisions / answers /
  notifications / approvals / action_plans / action_intents / executions /
  audit_logs / source_health
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Optional

log = logging.getLogger("ua.persistence")

SCHEMA_VERSION = 2

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    data TEXT NOT NULL,            -- WatchTask JSON
    state TEXT NOT NULL,
    next_scan_at TEXT,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS scan_runs (
    run_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    data TEXT NOT NULL             -- ScanRun JSON
);
CREATE INDEX IF NOT EXISTS idx_scan_runs_task ON scan_runs(task_id);

CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    data TEXT NOT NULL             -- EventEnvelope JSON
);
CREATE TABLE IF NOT EXISTS event_outbox (
    outbox_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL,
    data TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING',   -- PENDING/DELIVERED/DEAD
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS candidates (
    candidate_id TEXT PRIMARY KEY,
    domain TEXT NOT NULL,
    task_id TEXT,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS offers (
    offer_id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS quotes (
    quote_id TEXT PRIMARY KEY,
    offer_id TEXT NOT NULL,
    data TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS observations (
    observation_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS memories (
    record_id TEXT PRIMARY KEY,
    scope TEXT NOT NULL,
    key TEXT NOT NULL,
    task_id TEXT,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS preferences (
    record_id TEXT PRIMARY KEY,
    scope TEXT NOT NULL,
    key TEXT NOT NULL,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS decisions (
    record_id TEXT PRIMARY KEY,
    task_id TEXT,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS answers (
    record_id TEXT PRIMARY KEY,
    task_id TEXT,
    key TEXT NOT NULL,
    data TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notifications (
    fingerprint TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS approvals (
    approval_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS action_plans (
    plan_id TEXT PRIMARY KEY,
    task_id TEXT,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS action_intents (
    intent_id TEXT PRIMARY KEY,
    plan_id TEXT,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS executions (
    run_id TEXT PRIMARY KEY,
    intent_id TEXT,
    data TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_logs (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    action TEXT NOT NULL,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS source_health (
    marketplace_id TEXT PRIMARY KEY,
    data TEXT NOT NULL
);

-- P1.1: DB-backed Run Lease（多进程防双运行）
CREATE TABLE IF NOT EXISTS run_leases (
    task_id TEXT PRIMARY KEY,
    lease_owner TEXT NOT NULL,
    lease_token TEXT NOT NULL,
    acquired_at TEXT NOT NULL,
    heartbeat_at TEXT NOT NULL,
    lease_expires_at TEXT NOT NULL
);
"""


class Database:
    """SQLite + WAL 连接管理。单写者 + 多读者（WAL 允许并发读）。"""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=30000")
        return conn

    def _init(self) -> None:
        conn = self._connect()
        try:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version < SCHEMA_VERSION:
                conn.executescript(SCHEMA)
                conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
                conn.commit()
                log.info("schema initialized to v%s", SCHEMA_VERSION)
        finally:
            conn.close()

    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = self._connect()
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def execute(self, sql: str, params: tuple = ()):
        conn = self.conn()
        cur = conn.execute(sql, params)
        conn.commit()
        return cur

    def query_one(self, sql: str, params: tuple = ()) -> Optional[sqlite3.Row]:
        return self.conn().execute(sql, params).fetchone()

    def query_all(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        return self.conn().execute(sql, params).fetchall()
