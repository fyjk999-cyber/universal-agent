"""P1.3 回归测试：ScanRun 真实重试循环（backoff 到期自动重试）。"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from universal_agent.coordinator.scheduler import WatchDaemon
from universal_agent.coordinator.task_registry import TaskRegistry
from universal_agent.coordinator.task_registry.scanruns import ScanRunRepository
from universal_agent.core.contracts import ScanRunStatus, WatchState, WatchTask


def _task() -> WatchTask:
    return WatchTask(
        id="t1", type="watch", domain="flight",
        schedule={"timezone": "Asia/Shanghai", "baseline": ["09:00"]},
        state=WatchState.WATCHING,
        next_scan_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )


class TestRetryLoop:
    @pytest.mark.asyncio
    async def test_backoff_expired_triggers_retry(self, tmp_path):
        """FAILED_RETRYABLE 且 next_retry_at 已到 → 重试执行。"""
        reg = TaskRegistry(tmp_path / "reg")
        runs = ScanRunRepository(tmp_path / "runs")
        task = _task()
        # 防止 due_tasks 干扰：next_scan_at 设为未来
        task.next_scan_at = datetime.now(timezone.utc) + timedelta(hours=1)
        reg.create(task)
        attempts = []

        async def flaky_runner(t):
            attempts.append("run")
            if len(attempts) == 1:
                raise TimeoutError("first attempt fails")
            return {"ok": True}

        daemon = WatchDaemon(reg, scan_runs=runs, tick_seconds=60, runner=flaky_runner)
        # 第一次执行 → FAILED_RETRYABLE
        await daemon._run_task(task)
        latest = runs.latest_for("t1")
        assert latest.status == ScanRunStatus.FAILED_RETRYABLE

        # 手动把 next_retry_at 设为过去（模拟 backoff 到期）
        import json as _json
        from datetime import timedelta as _td
        data = tmp_path / "runs" / "scan_runs.json"
        raw = _json.loads(data.read_text("utf-8"))
        raw[latest.run_id]["next_retry_at"] = (datetime.now(timezone.utc) - _td(seconds=1)).isoformat()
        data.write_text(_json.dumps(raw), "utf-8")
        runs._load()

        # 重试循环 → 执行成功
        await daemon._retry_failed_runs()
        assert len(attempts) == 2
        latest2 = runs.latest_for("t1")
        assert latest2.status == ScanRunStatus.SUCCESS
        assert latest2.attempt == 2  # 第 2 次尝试成功

    @pytest.mark.asyncio
    async def test_cancelled_task_not_retried(self, tmp_path):
        """任务已取消 → 不重试。"""
        reg = TaskRegistry(tmp_path / "reg")
        runs = ScanRunRepository(tmp_path / "runs")
        task = _task()
        task.state = WatchState.CANCELLED
        reg.create(task)
        run = runs.start("t1")
        from datetime import timedelta as _td
        run.next_retry_at = datetime.now(timezone.utc) - _td(seconds=1)
        runs.finish(run.run_id, ScanRunStatus.FAILED_RETRYABLE, error_type="source_unavailable")
        # 强制 next_retry_at 过去
        import json as _json
        data = tmp_path / "runs" / "scan_runs.json"
        raw = _json.loads(data.read_text("utf-8"))
        raw[run.run_id]["next_retry_at"] = (datetime.now(timezone.utc) - _td(seconds=1)).isoformat()
        data.write_text(_json.dumps(raw), "utf-8")
        runs._load()

        daemon = WatchDaemon(reg, scan_runs=runs, tick_seconds=60)
        await daemon._tick()  # 不应崩溃，也不应重试已取消任务
        assert runs.latest_for("t1").status == ScanRunStatus.FAILED_RETRYABLE
