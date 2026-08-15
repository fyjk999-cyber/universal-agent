"""P1.1b — WatchDaemon Runtime Unification：SQLite 唯一真相源。

先写失败测试（RED），再实现（GREEN）。

验收点：
1. load_watch_daemon 用 SQLite Repository，不再创建 JSON task_registry.json
2. 跨重启 Task 状态保留（SQLite 真相）
3. Daemon 与 Host/Coordinator 看到同一 Task 状态（同一 Repository Set）
4. 无 JSON dual truth：data/ 下无 task_registry.json / scan_runs 目录
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from universal_agent.coordinator.scheduler import load_watch_daemon
from universal_agent.coordinator.task_coordinator import TaskCoordinator
from universal_agent.persistence import Database
from universal_agent.persistence import SqliteTaskRepository

TASKS_DIR = Path(__file__).resolve().parent.parent.parent / "tasks"
WATCH_ID = "queenstown-travel-watch"


def _load(tmp_path: Path, data_sub: str = "data"):
    data_dir = tmp_path / data_sub
    return asyncio.run(load_watch_daemon(TASKS_DIR, data_dir, runner=None)), data_dir


def test_no_json_dual_state(tmp_path: Path) -> None:
    """P1.1：load_watch_daemon 不得创建 JSON registry / scan_runs 文件。"""
    daemon, data_dir = _load(tmp_path)
    registry_file = data_dir / "registry" / "task_registry.json"
    scanruns_dir = data_dir / "scan_runs"
    assert not registry_file.exists(), f"JSON dual state 仍存在: {registry_file}"
    assert not scanruns_dir.exists(), f"JSON scan_runs 仍存在: {scanruns_dir}"
    # SQLite 是唯一真相
    assert (data_dir / "universal_agent.db").exists()


def test_tasks_in_sqlite_after_load(tmp_path: Path) -> None:
    """任务写入 SQLite（tasks 表），而非 JSON。"""
    daemon, data_dir = _load(tmp_path)
    db = Database(data_dir / "universal_agent.db")
    row = db.query_one("SELECT data FROM tasks WHERE id=?", (WATCH_ID,))
    assert row is not None, "task 不在 SQLite tasks 表"
    data = json.loads(row["data"])
    assert data["id"] == WATCH_ID
    db.close()


def test_restart_preserves_task_in_sqlite(tmp_path: Path) -> None:
    """跨重启：Task 状态从 SQLite 恢复（不依赖 JSON）。"""
    d1, data_dir = _load(tmp_path)
    task = d1.registry.get(WATCH_ID)
    assert task is not None
    # 修改状态模拟运行后
    from universal_agent.core.state_machine import transition
    from universal_agent.core.contracts import WatchState
    task.state = transition(task.state, WatchState.ACTIVE)
    task.scan_count += 1
    d1.registry.update(task)

    d2, _ = _load(tmp_path)  # 重启
    revived = d2.registry.get(WATCH_ID)
    assert revived is not None
    assert revived.scan_count == 1
    assert revived.state.value == "ACTIVE"


def test_daemon_and_host_share_repository_set(tmp_path: Path) -> None:
    """P1.1：Daemon 与 Host 使用同一 Repository Set（同一 DB）。"""
    daemon, data_dir = _load(tmp_path)
    db = Database(data_dir / "universal_agent.db")
    repo = SqliteTaskRepository(db)
    coordinator = TaskCoordinator(repo)
    # Host 通过 Coordinator 读取 → 与 daemon 看到同一 Task
    host_task = coordinator.get(WATCH_ID)
    daemon_task = daemon.registry.get(WATCH_ID)
    assert host_task is not None and daemon_task is not None
    assert host_task.id == daemon_task.id == WATCH_ID
    db.close()
