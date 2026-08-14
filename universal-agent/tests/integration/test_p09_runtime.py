"""P0.9-8 集成测试 1：Watch 运行时 — retry/backoff/restart 闭环。"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from universal_agent.coordinator.scheduler import WatchDaemon
from universal_agent.coordinator.task_registry import TaskRegistry
from universal_agent.coordinator.task_registry.scanruns import ScanRunRepository
from universal_agent.core.contracts import ScanRunStatus, WatchState, WatchTask


def _task() -> WatchTask:
    return WatchTask(
        id="rt-watch", type="watch", domain="flight",
        schedule={"timezone": "Asia/Shanghai", "baseline": ["09:00"]},
        state=WatchState.WATCHING,
        next_scan_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )


def _force_retry_due(runs: ScanRunRepository, run_id: str) -> None:
    data = runs.data_dir / "scan_runs.json"
    raw = json.loads(data.read_text("utf-8"))
    raw[run_id]["next_retry_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    data.write_text(json.dumps(raw), "utf-8")
    runs._load()


class TestRuntimeFlow:
    @pytest.mark.asyncio
    async def test_full_runtime_loop(self, tmp_path):
        """创建 → 失败 → Watch 存活 → backoff → retry 成功 → 恢复 baseline → restart。"""
        reg = TaskRegistry(tmp_path / "reg")
        runs = ScanRunRepository(tmp_path / "runs")
        task = _task()
        reg.create(task)
        attempts = []

        async def flaky(t):
            attempts.append("run")
            if len(attempts) == 1:
                raise TimeoutError("source timeout")
            return {"ok": True}

        daemon = WatchDaemon(reg, scan_runs=runs, tick_seconds=60, runner=flaky)

        # 1) 首次扫描 → 源超时
        await daemon._run_task(task)
        assert runs.latest_for(task.id).status == ScanRunStatus.FAILED_RETRYABLE
        # 2) Watch 保持 WATCHING（临时失败不死 Watch）
        assert reg.get(task.id).state == WatchState.WATCHING
        # 3) next_retry_at 未到 → tick 不重试
        await daemon._tick()
        assert len(attempts) == 1
        # 4) backoff 到期 → 自动 retry
        latest = runs.latest_for(task.id)
        _force_retry_due(runs, latest.run_id)
        await daemon._retry_failed_runs()
        assert len(attempts) == 2
        assert runs.latest_for(task.id).status == ScanRunStatus.SUCCESS
        # 5) 恢复 baseline schedule（next_scan_at 未来）
        refreshed = reg.get(task.id)
        assert refreshed.next_scan_at > datetime.now(timezone.utc)

    @pytest.mark.asyncio
    async def test_restart_keeps_retry_state(self, tmp_path):
        """restart 后 retry/task 状态仍存在（跨重启不丢）。"""
        d = tmp_path / "data"
        reg1 = TaskRegistry(d / "reg")
        runs1 = ScanRunRepository(d / "runs")
        task = _task()
        reg1.create(task)

        async def flaky(t):
            raise TimeoutError("down")

        daemon1 = WatchDaemon(reg1, scan_runs=runs1, tick_seconds=60, runner=flaky)
        await daemon1._run_task(task)
        del daemon1, reg1, runs1

        # 重启
        reg2 = TaskRegistry(d / "reg")
        runs2 = ScanRunRepository(d / "runs")
        assert reg2.get(task.id) is not None  # task 仍在
        latest = runs2.latest_for(task.id)
        assert latest is not None
        assert latest.status == ScanRunStatus.FAILED_RETRYABLE  # retry 状态保留
        assert latest.next_retry_at is not None
