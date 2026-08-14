"""调度守护测试（§15/§48/§60）：tick / 多任务 / 失败隔离 / 重启恢复。"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from universal_agent.coordinator import TaskRegistry
from universal_agent.coordinator.scheduler import BaselineScheduler, WatchDaemon
from universal_agent.core.contracts import WatchState, WatchTask


def _task(task_id: str, baseline: list[str]) -> WatchTask:
    return WatchTask(
        id=task_id, type="watch", domain="flight",
        schedule={"timezone": "Asia/Shanghai", "baseline": baseline},
        state=WatchState.WATCHING,
    )


class TestWatchDaemon:
    def test_due_tasks_detection(self, tmp_path):
        reg = TaskRegistry(tmp_path / "reg")
        t = _task("t1", ["09:00"])
        t.next_scan_at = None
        # 手动设定 next_scan_at = 今天 09:00
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        t.next_scan_at = now.replace(hour=9, minute=0, second=0, microsecond=0)
        reg.create(t)
        daemon = WatchDaemon(reg, tick_seconds=60)
        due = daemon.registry.due_tasks_utc(now)
        assert t.id in due

    @pytest.mark.asyncio
    async def test_tick_runs_due_task(self, tmp_path):
        reg = TaskRegistry(tmp_path / "reg")
        t = _task("t1", ["09:00"])
        t.next_scan_at = None
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        t.next_scan_at = now.replace(hour=9, minute=0, second=0, microsecond=0)
        reg.create(t)
        ran = []

        async def runner(task):
            ran.append(task.id)
            return {"ok": True}

        daemon = WatchDaemon(reg, tick_seconds=60, runner=runner)
        await daemon._tick()
        assert ran == ["t1"]
        # 扫描后推进 next_scan_at（下次不是 09:00 而是明天）
        refreshed = reg.get("t1")
        assert refreshed.scan_count == 1
        assert refreshed.next_scan_at is not None

    @pytest.mark.asyncio
    async def test_failure_marks_failed_does_not_crash(self, tmp_path):
        """§48: 单任务失败 → FAILED 状态，不中断 daemon。"""
        reg = TaskRegistry(tmp_path / "reg")
        t = _task("t1", ["09:00"])
        t.next_scan_at = None
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        t.next_scan_at = now.replace(hour=9, minute=0, second=0, microsecond=0)
        reg.create(t)

        async def bad_runner(task):
            raise RuntimeError("source down")

        daemon = WatchDaemon(reg, tick_seconds=60, runner=bad_runner)
        await daemon._tick()  # 必须不抛异常
        refreshed = reg.get("t1")
        assert refreshed.state == WatchState.FAILED

    def test_multitask_loading(self, tmp_path):
        """从 tasks/ 加载所有 watch 任务（多任务支持）。"""
        import asyncio
        from universal_agent.coordinator.scheduler import load_watch_daemon

        async def go():
            daemon = await load_watch_daemon(
                Path(__file__).resolve().parent.parent.parent / "tasks",
                tmp_path / "data", runner=None)
            ids = [t.id for t in daemon.registry.list()]
            return ids

        ids = asyncio.run(go())
        assert "queenstown-travel-watch" in ids

    def test_restart_recovery(self, tmp_path):
        """§60: 进程重启后任务从 registry 恢复。"""
        import asyncio
        from universal_agent.coordinator.scheduler import load_watch_daemon

        async def first():
            d = await load_watch_daemon(
                Path(__file__).resolve().parent.parent.parent / "tasks",
                tmp_path / "data", runner=None)
            return d

        d1 = asyncio.run(first())

        async def second():
            d2 = await load_watch_daemon(
                Path(__file__).resolve().parent.parent.parent / "tasks",
                tmp_path / "data", runner=None)
            return d2

        d2 = asyncio.run(second())
        # 重启后任务仍在
        assert d2.registry.get("queenstown-travel-watch") is not None
