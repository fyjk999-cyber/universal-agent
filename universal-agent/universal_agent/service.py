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

    # 后续 Sprint（P4+）：events/observations/notifications/approvals/
    # actions/audit/source_health 全部并入此处，共享同一 db。


class UniversalAgentService:
    def __init__(self, data_dir: Path,
                 host: str = "deepseek_harness",
                 db_path: Optional[Path] = None) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db = Database(db_path or (self.data_dir / "universal_agent.db"))
        self.repos = RepositorySet(self.db)
        self.coordinator = TaskCoordinator(self.repos.tasks)
        if host == "deepseek_harness":
            from .hosts.deepseek_harness.adapter import HarnessHostAdapter
            self.adapter = HarnessHostAdapter(coordinator=self.coordinator)
        elif host == "jarvis":
            from .hosts.jarvis.adapter import MockJarvisHostAdapter
            self.adapter = MockJarvisHostAdapter(coordinator=self.coordinator)
        else:
            raise ValueError(f"unknown host: {host}")

    def close(self) -> None:
        self.db.close()
