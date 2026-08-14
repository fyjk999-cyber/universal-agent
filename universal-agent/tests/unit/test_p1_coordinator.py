"""P1.6 回归测试：TaskCoordinator 命令模式（Host 不存真相）。"""
from __future__ import annotations

import pytest

from universal_agent.coordinator.task_coordinator import TaskCoordinator, sqlite_task_coordinator
from universal_agent.core.contracts import WatchState, WatchTask
from universal_agent.persistence import Database, SqliteTaskRepository


def _task(task_id: str = "t1") -> WatchTask:
    return WatchTask(
        id=task_id, type="watch", domain="flight",
        schedule={"timezone": "Asia/Shanghai", "baseline": ["09:00"]},
        state=WatchState.DRAFT,
    )


class TestTaskCoordinator:
    def test_command_flow(self, tmp_path):
        coord = sqlite_task_coordinator(tmp_path / "ua.db")
        t = coord.create_watch(_task())
        assert t.state == WatchState.DRAFT
        active = coord.activate("t1")
        assert active.state == WatchState.ACTIVE
        paused = coord.pause("t1")
        assert paused.state == WatchState.PAUSED
        resumed = coord.resume("t1")
        assert resumed.state == WatchState.WATCHING

    def test_invalid_transition_rejected(self, tmp_path):
        """coordinator 只暴露合法命令；状态机校验由 transition() 保证。"""
        coord = sqlite_task_coordinator(tmp_path / "ua.db")
        coord.create_watch(_task())
        # cancel 从 DRAFT → CANCELLED 合法
        assert coord.cancel("t1").state == WatchState.CANCELLED
        # 已取消的任务 resume 是 no-op（不复活终端态）
        assert coord.resume("t1").state == WatchState.CANCELLED

    def test_host_does_not_own_task_truth(self, tmp_path):
        """P1.2 核心：Host adapter 不再有 tasks.json 独立真相。"""
        db_path = tmp_path / "ua.db"
        coord = sqlite_task_coordinator(db_path)
        coord.create_watch(_task())
        # 真相在 SQLite，不在任何 JSON
        assert not (tmp_path / "tasks.json").exists()
        # 通过新连接仍可读（单一真相）
        db = Database(db_path)
        assert SqliteTaskRepository(db).get("t1") is not None

    def test_list_and_get(self, tmp_path):
        coord = sqlite_task_coordinator(tmp_path / "ua.db")
        coord.create_watch(_task("a"))
        coord.create_watch(_task("b"))
        assert {t.id for t in coord.list()} == {"a", "b"}
