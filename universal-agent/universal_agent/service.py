"""UniversalAgentService（P1.1d）— 统一装配入口。

聚合：
  - 单一 SQLite Database（唯一 Runtime Truth）
  - Repository Set（tasks/scan_runs/events/memory/... 全部指向同一 DB）
  - TaskCoordinator（命令模式：Host 唯一写入入口）
  - RunLease（DB-backed，多进程防双运行）
  - Host Adapter（当前 DeepSeek Harness；未来 Jarvis 同构替换）

依赖方向（NON-NEGOTIABLE）：
  Host → HarnessHostAdapter → UniversalAgentService
        → Coordinator → StateMachine → Repository(SQLite)
  Core 永不依赖 Host。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from .coordinator.task_coordinator import TaskCoordinator
from .hosts.deepseek_harness.adapter import HarnessHostAdapter
from .persistence import (
    Database,
    SqliteTaskRepository,
    SqliteScanRunRepository,
)

log = logging.getLogger("ua.service")


class RepositorySet:
    """统一 Repository Set（全部指向同一 Database）。"""

    def __init__(self, db: Database) -> None:
        self.db = db
        self.tasks = SqliteTaskRepository(db)
        self.scan_runs = SqliteScanRunRepository(db)
        # P3: Memory（8 子域类型化访问器）
        from .memory.domains import MemoryDomains
        from .memory.sqlite_store import SqliteMemoryStore
        self.memory = MemoryDomains(SqliteMemoryStore(db))
        # P23（FR-031 / RULE-003）：全部 Repository 并入单一 SQLite
        from .persistence import (
            SqliteActionRepository,
            SqliteApprovalRepository,
            SqliteAuditRepository,
            SqliteEventRepository,
            SqliteKvRepository,
            SqliteNotificationRepository,
            SqliteObservationRepository,
            SqliteOutboxRepository,
            SqliteSourceHealthRepository,
        )
        self.events = SqliteEventRepository(db)
        self.outbox = SqliteOutboxRepository(db)
        self.observations = SqliteObservationRepository(db)
        self.notifications = SqliteNotificationRepository(db)
        self.approvals = SqliteApprovalRepository(db)
        self.actions = SqliteActionRepository(db)
        self.audit = SqliteAuditRepository(db)
        self.source_health = SqliteSourceHealthRepository(db)
        # RULE-003：idempotency / 通知去重 / KillSwitch 状态（Kv 表）
        self.idempotency_kv = SqliteKvRepository(db, "idempotency")
        self.dedup_kv = SqliteKvRepository(db, "notification_dedup")
        self.killswitch_kv = SqliteKvRepository(db, "killswitch")

    # 后续 Sprint（P4+）：events/observations/notifications/approvals/
    # actions/audit/source_health 全部并入此处，共享同一 db。


class UniversalAgentService:
    def __init__(self, data_dir: Path,
                 host: str = "deepseek_harness",
                 db_path: Optional[Path] = None,
                 scan_runner=None) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db = Database(db_path or (self.data_dir / "universal_agent.db"))
        self.repos = RepositorySet(self.db)
        self.coordinator = TaskCoordinator(self.repos.tasks)
        # P4: Observability（metrics/traces/logs/audit）
        from .observability import AuditLog, MetricsRegistry, StructuredLog, Tracer
        self.metrics = MetricsRegistry(self.data_dir / "metrics.json")
        self.traces = Tracer(self.data_dir / "traces.jsonl")
        self.logs = StructuredLog(self.data_dir / "logs.jsonl")
        self.audit = AuditLog(self.data_dir / "audit")
        # P23（FR-030/031/032 + RULE-003）：Host 适配器装配 scan_runs + notifications +
        # approval inbox；SQLite-backed 幂等/去重/KillSwitch 状态
        from .actions.approval import ApprovalInbox
        from .actions.idempotency import IdempotencyStore
        from .actions.policy import KillSwitch
        from .notifications import NotificationDedup
        self.approval_inbox = ApprovalInbox(repo=self.repos.approvals)
        self.idempotency = IdempotencyStore(repo=self.repos.idempotency_kv)
        self.notification_dedup = NotificationDedup(repo=self.repos.dedup_kv)
        self.killswitch = KillSwitch(repo=self.repos.killswitch_kv)
        adapter_kw = dict(coordinator=self.coordinator,
                          scan_runs=self.repos.scan_runs,
                          notifications=self.repos.notifications,
                          approval_inbox=self.approval_inbox,
                          scan_runner=scan_runner)
        if host == "deepseek_harness":
            from .hosts.deepseek_harness.adapter import HarnessHostAdapter
            self.adapter = HarnessHostAdapter(**adapter_kw)
        elif host == "jarvis":
            from .hosts.jarvis.adapter import MockJarvisHostAdapter
            self.adapter = MockJarvisHostAdapter(**adapter_kw)
        else:
            raise ValueError(f"unknown host: {host}")

    def close(self) -> None:
        self.db.close()
