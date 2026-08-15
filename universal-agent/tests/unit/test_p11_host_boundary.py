"""P1.1c — Host Write Boundary：Host 不得直接 repo.update()。

Host 唯一入口是 Command（create/pause/resume/cancel/apply_update），
全部经 TaskCoordinator → StateMachine → Repository。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from universal_agent.core.contracts import WatchState
from universal_agent.core.state_machine import TransitionError
from universal_agent.coordinator.task_coordinator import TaskCoordinator
from universal_agent.hosts.deepseek_harness.adapter import HarnessHostAdapter
from universal_agent.persistence import Database, SqliteTaskRepository


def _make_task():
    from universal_agent.core.contracts import WatchTask, WatchState
    return WatchTask(
        id="t1", type="watch", domain="flight",
        schedule={"timezone": "Asia/Shanghai", "baseline": ["09:00"]},
        state=WatchState.DRAFT,
    )


def test_host_update_task_goes_through_coordinator(tmp_path: Path) -> None:
    """update_task 必须经 Coordinator 命令，非法状态转移被拒绝。"""
    db = Database(tmp_path / "ua.db")
    repo = SqliteTaskRepository(db)
    coord = TaskCoordinator(repo)
    adapter = HarnessHostAdapter(coordinator=coord)

    task = _make_task()
    created = adapter.create_task(task)
    assert created.state == WatchState.DRAFT

    # Host 试图 DRAFT → FAILED（非法转移）→ 必须被拒绝
    task.state = WatchState.FAILED
    with pytest.raises(TransitionError):
        adapter.update_task(task)

    # 合法转移 DRAFT → ACTIVE 成功
    task.state = WatchState.ACTIVE
    updated = adapter.update_task(task)
    assert updated.state == WatchState.ACTIVE
    db.close()


def test_host_has_no_direct_repo_write(tmp_path: Path) -> None:
    """Host 内部不得出现 coordinator.repo.update 调用路径。"""
    import inspect
    from universal_agent.hosts.deepseek_harness import adapter as adapter_mod
    src = inspect.getsource(adapter_mod)
    # update_task 不能直接碰 repo
    assert "coordinator.repo.update" not in src


def test_direct_repo_update_skipped_if_no_coordinator(tmp_path: Path) -> None:
    """未装配 Coordinator 时 update_task 报错（fail-closed，不静默写 JSON）。"""
    adapter = HarnessHostAdapter(coordinator=None)
    from universal_agent.coordinator.task_coordinator import TaskCommandError
    with pytest.raises(TaskCommandError):
        adapter.update_task(_make_task())
