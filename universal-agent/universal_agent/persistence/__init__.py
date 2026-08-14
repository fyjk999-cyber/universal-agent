"""persistence package — SQLite + WAL 单一真相源（P1）."""
from __future__ import annotations

from pathlib import Path

from .repos import (
    SqliteActionRepository,
    SqliteApprovalRepository,
    SqliteAuditRepository,
    SqliteEventRepository,
    SqliteMemoryRepository,
    SqliteNotificationRepository,
    SqliteObservationRepository,
    SqliteOutboxRepository,
    SqliteSourceHealthRepository,
)
from .scanrun_repo import SqliteScanRunRepository
from .sqlite import Database
from .task_repo import SqliteTaskRepository

__all__ = [
    "Database",
    "SqliteActionRepository",
    "SqliteApprovalRepository",
    "SqliteAuditRepository",
    "SqliteEventRepository",
    "SqliteMemoryRepository",
    "SqliteNotificationRepository",
    "SqliteObservationRepository",
    "SqliteOutboxRepository",
    "SqliteScanRunRepository",
    "SqliteSourceHealthRepository",
    "SqliteTaskRepository",
]


def open_database(path: Path) -> Database:
    return Database(path)
