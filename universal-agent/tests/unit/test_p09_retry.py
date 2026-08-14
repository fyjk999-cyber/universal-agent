"""P0.9-1 回归测试：ScanRun Retry 真正接入 WatchDaemon。

规则：
- retry 由 next_retry_at 驱动（backoff 未到不运行）
- 防 baseline+retry 双启动（RunGuard + pending-retry 检查）
- backoff: 1m/5m/15m/1h，跨重启保持 retry chain
- retry 成功 → 恢复正常 baseline 调度
- RUNNING 的 task 不能再次启动 ScanRun
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from universal_agent.coordinator.scheduler import WatchDaemon
from universal_agent.coordinator.scheduler.runguard import RunningTaskGuard
from universal_agent.coordinator.task_registry import TaskRegistry
from universal_agent.coordinator.task_registry.scanruns import ScanRunRepository
from universal_agent.core.contracts import ScanRunStatus, WatchState, WatchTask
from universal_agent.core.contracts.scanrun import RETRY_BACKOFF


def _task(next_in_past: bool = True) -> WatchTask:
    nxt = datetime.now(timezone.utc) - timedelta(minutes=1) if next_in_past else \
        datetime.now(timezone.utc) + timedelta(hours=1)
    return WatchTask(
        id="t1", type="watch", domain="flight",
        schedule={"timezone": "Asia/Shanghai", "baseline": ["09:00"]},
        state=WatchState.WATCHING, next_scan_at=nxt,
    )


def _force_retry_due(runs: ScanRunRepository, run_id: str) -> None:
    """把 next_retry_at 强制设为过去（模拟 backoff 到期）。"""
    data = runs.data_dir / "scan_runs.json"
    raw = json.loads(data.read_text("utf-8"))
    raw[run_id]["next_retry_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    data.write_text(json.dumps(raw), "utf-8")
    runs._load()


class TestRetryScheduling:
    @pytest.mark.asyncio
    async def test_retry_not_before_next_retry_at(self, tmp_path):
        """backoff 未到期 → 不重试（即使 next_scan_at 过期）。"""
        reg = TaskRegistry(tmp_path / "reg")
        runs = ScanRunRepository(tmp_path / "runs")
        task = _task()
        reg.create(task)
        attempts = []

        async def flaky(t):
            attempts.append("run")
            raise TimeoutError("down")

        daemon = WatchDaemon(reg, scan_runs=runs, tick_seconds=60, runner=flaky)
        await daemon._run_task(task)  # 第 1 次失败
        assert len(attempts) == 1
        # next_retry_at 未到期 → tick 不重试
        await daemon._tick()
        assert len(attempts) == 1  # 未重试（backoff 1m 未到）

    @pytest.mark.asyncio
    async def test_retry_runs_when_next_retry_at_due(self, tmp_path):
        reg = TaskRegistry(tmp_path / "reg")
        runs = ScanRunRepository(tmp_path / "runs")
        task = _task()
        reg.create(task)
        attempts = []

        async def flaky(t):
            attempts.append("run")
            if len(attempts) == 1:
                raise TimeoutError("down")
            return {"ok": True}

        daemon = WatchDaemon(reg, scan_runs=runs, tick_seconds=60, runner=flaky)
        await daemon._run_task(task)
        latest = runs.latest_for("t1")
        _force_retry_due(runs, latest.run_id)
        await daemon._retry_failed_runs()
        assert len(attempts) == 2
        assert runs.latest_for("t1").status == ScanRunStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_first_retry_waits_1_minute(self, tmp_path):
        repo = ScanRunRepository(tmp_path / "runs")
        run = repo.start("t1")
        done = repo.finish(run.run_id, ScanRunStatus.FAILED_RETRYABLE, error_type="timeout")
        delta = (done.next_retry_at - done.finished_at).total_seconds()
        assert 50 < delta <= 70  # ~1m

    @pytest.mark.asyncio
    async def test_second_retry_waits_5_minutes(self, tmp_path):
        repo = ScanRunRepository(tmp_path / "runs")
        run = repo.start("t1")
        for _ in range(2):
            run = repo.finish(run.run_id, ScanRunStatus.FAILED_RETRYABLE, error_type="timeout")
        delta = (run.next_retry_at - run.finished_at).total_seconds()
        assert 280 < delta <= 320  # ~5m

    @pytest.mark.asyncio
    async def test_third_retry_waits_15_minutes(self, tmp_path):
        repo = ScanRunRepository(tmp_path / "runs")
        run = repo.start("t1")
        for _ in range(3):
            run = repo.finish(run.run_id, ScanRunStatus.FAILED_RETRYABLE, error_type="timeout")
        delta = (run.next_retry_at - run.finished_at).total_seconds()
        assert 850 < delta <= 950  # ~15m

    @pytest.mark.asyncio
    async def test_fourth_retry_waits_1_hour(self, tmp_path):
        repo = ScanRunRepository(tmp_path / "runs")
        run = repo.start("t1")
        for _ in range(4):
            run = repo.finish(run.run_id, ScanRunStatus.FAILED_RETRYABLE, error_type="timeout")
        delta = (run.next_retry_at - run.finished_at).total_seconds()
        assert 3500 < delta <= 3700  # ~1h
        assert RETRY_BACKOFF == [60, 300, 900, 3600]

    @pytest.mark.asyncio
    async def test_retry_count_survives_restart(self, tmp_path):
        """retry chain 跨重启保持（retry_of_run_id）。"""
        d = tmp_path / "runs"
        r1 = ScanRunRepository(d)
        run = r1.start("t1")
        for _ in range(2):
            run = r1.finish(run.run_id, ScanRunStatus.FAILED_RETRYABLE, error_type="timeout")
        assert run.retry_count == 2
        del r1
        r2 = ScanRunRepository(d)
        latest = r2.latest_for("t1")
        assert latest.retry_count == 2  # 重启后不归零
        # start_retry 继承 chain
        retry_run = r2.start_retry("t1", latest.run_id)
        assert retry_run.retry_count == 3
        assert retry_run.retry_of_run_id == latest.run_id

    @pytest.mark.asyncio
    async def test_retry_and_baseline_do_not_double_run(self, tmp_path):
        """pending retry 时 baseline 跳过 → 不双启动。"""
        reg = TaskRegistry(tmp_path / "reg")
        runs = ScanRunRepository(tmp_path / "runs")
        task = _task()
        reg.create(task)
        attempts = []

        async def flaky(t):
            attempts.append("run")
            raise TimeoutError("down")

        daemon = WatchDaemon(reg, scan_runs=runs, tick_seconds=60, runner=flaky)
        await daemon._run_task(task)  # 失败 → pending retry
        # next_scan_at 已推进到未来（失败时也推进），retry 未到期
        await daemon._tick()
        assert len(attempts) == 1  # 不因 baseline 重复运行

    @pytest.mark.asyncio
    async def test_running_task_cannot_start_second_scanrun(self, tmp_path):
        """RunGuard：RUNNING 的 task 不能再次启动。"""
        guard = RunningTaskGuard()
        assert guard.try_acquire("t1") is True
        assert guard.try_acquire("t1") is False  # 已占用
        guard.release("t1")
        assert guard.try_acquire("t1") is True

    @pytest.mark.asyncio
    async def test_successful_retry_returns_to_baseline_schedule(self, tmp_path):
        """retry 成功 → 清除 retry 状态，恢复 baseline（next_scan_at 为未来）。"""
        reg = TaskRegistry(tmp_path / "reg")
        runs = ScanRunRepository(tmp_path / "runs")
        task = _task()
        reg.create(task)
        attempts = []

        async def flaky(t):
            attempts.append("run")
            if len(attempts) == 1:
                raise TimeoutError("down")
            return {"ok": True}

        daemon = WatchDaemon(reg, scan_runs=runs, tick_seconds=60, runner=flaky)
        await daemon._run_task(task)  # 失败
        latest = runs.latest_for("t1")
        _force_retry_due(runs, latest.run_id)
        await daemon._retry_failed_runs()  # 重试成功
        assert runs.latest_for("t1").status == ScanRunStatus.SUCCESS
        refreshed = reg.get("t1")
        assert refreshed.next_scan_at is not None
        assert refreshed.next_scan_at > datetime.now(timezone.utc)  # 恢复未来 baseline
