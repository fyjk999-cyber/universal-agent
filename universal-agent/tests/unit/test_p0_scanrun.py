"""P0.2 回归测试：Task 与 ScanRun 状态分离。

规则：平台临时失败 → ScanRun FAILED_RETRYABLE + backoff；
Watch 保持 WATCHING。仅致命错误才 Watch=FAILED。
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from universal_agent.coordinator.scheduler import WatchDaemon
from universal_agent.coordinator.task_registry import TaskRegistry
from universal_agent.coordinator.task_registry.scanruns import (
    ScanRunRepository,
    classify_error,
    is_fatal,
    is_retryable,
)
from universal_agent.core.contracts import ScanRunStatus, WatchState, WatchTask


def _task() -> WatchTask:
    return WatchTask(
        id="t1", type="watch", domain="flight",
        schedule={"timezone": "Asia/Shanghai", "baseline": ["09:00", "15:00", "21:00"]},
        state=WatchState.WATCHING,
        next_scan_at=datetime.now(timezone.utc) - timedelta(minutes=1),  # 已到期
    )


class TestScanRunRepo:
    def test_start_finish(self, tmp_path):
        repo = ScanRunRepository(tmp_path)
        run = repo.start("t1")
        assert run.status == ScanRunStatus.RUNNING
        done = repo.finish(run.run_id, ScanRunStatus.SUCCESS)
        assert done.status == ScanRunStatus.SUCCESS
        assert done.finished_at is not None

    def test_retryable_sets_backoff(self, tmp_path):
        repo = ScanRunRepository(tmp_path)
        run = repo.start("t1")
        failed = repo.finish(run.run_id, ScanRunStatus.FAILED_RETRYABLE,
                             error_type="source_unavailable")
        assert failed.retry_count == 1
        assert failed.next_retry_at is not None
        assert failed.next_retry_at > failed.finished_at  # 1m backoff

    def test_retryable_backoff_escalates(self, tmp_path):
        """backoff 递增：1m → 5m → 15m → 1h。"""
        repo = ScanRunRepository(tmp_path)
        run = repo.start("t1")
        for attempt in range(3):
            run = repo.finish(run.run_id, ScanRunStatus.FAILED_RETRYABLE,
                              error_type="source_unavailable")
        assert run.retry_count == 3
        # 第 3 次失败 backoff = 15m
        assert run.next_retry_at is not None
        delta = (run.next_retry_at - run.finished_at).total_seconds()
        assert 14 * 60 < delta <= 16 * 60

    def test_latest_for(self, tmp_path):
        repo = ScanRunRepository(tmp_path)
        r1 = repo.start("t1"); repo.finish(r1.run_id, ScanRunStatus.SUCCESS)
        r2 = repo.start("t1")
        latest = repo.latest_for("t1")
        assert latest.run_id == r2.run_id


class TestErrorClassification:
    def test_retryable_types(self):
        assert is_retryable("source_unavailable") is True
        assert is_retryable("rate_limit") is True
        assert is_retryable("browser_crash") is True
        assert is_retryable("fatal_validation") is False

    def test_classify(self):
        assert classify_error(TimeoutError("timeout")) == "source_unavailable"
        assert classify_error(ValueError("schema validation failed")) == "fatal_validation"
        assert is_fatal(ValueError("schema validation failed")) is True
        assert is_fatal(TimeoutError("x")) is False


class TestWatchSurvivesSourceFailure:
    @pytest.mark.asyncio
    async def test_source_failure_keeps_watch_alive(self, tmp_path):
        """§P0.2 核心：网络超时 → ScanRun FAILED_RETRYABLE，Watch 保持 WATCHING。"""
        reg = TaskRegistry(tmp_path / "reg")
        runs = ScanRunRepository(tmp_path / "runs")
        task = _task()
        reg.create(task)

        async def bad_runner(t):
            raise TimeoutError("network timeout")

        daemon = WatchDaemon(reg, scan_runs=runs, tick_seconds=60, runner=bad_runner)
        await daemon._run_task(task)

        refreshed = reg.get("t1")
        assert refreshed.state == WatchState.WATCHING  # Watch 不死
        latest = runs.latest_for("t1")
        assert latest.status == ScanRunStatus.FAILED_RETRYABLE
        assert latest.error_type == "source_unavailable"

    @pytest.mark.asyncio
    async def test_fatal_marks_watch_failed(self, tmp_path):
        """致命错误（schema 损坏）→ Watch=FAILED。"""
        reg = TaskRegistry(tmp_path / "reg")
        runs = ScanRunRepository(tmp_path / "runs")
        task = _task()
        reg.create(task)

        async def fatal_runner(t):
            raise ValueError("schema validation failed")

        daemon = WatchDaemon(reg, scan_runs=runs, tick_seconds=60, runner=fatal_runner)
        await daemon._run_task(task)

        refreshed = reg.get("t1")
        assert refreshed.state == WatchState.FAILED
        latest = runs.latest_for("t1")
        assert latest.status == ScanRunStatus.FAILED_FATAL

    @pytest.mark.asyncio
    async def test_success_advances_scan_count(self, tmp_path):
        reg = TaskRegistry(tmp_path / "reg")
        runs = ScanRunRepository(tmp_path / "runs")
        task = _task()
        reg.create(task)

        async def good_runner(t):
            return {"ok": True}

        daemon = WatchDaemon(reg, scan_runs=runs, tick_seconds=60, runner=good_runner)
        await daemon._run_task(task)
        refreshed = reg.get("t1")
        assert refreshed.scan_count == 1
        assert runs.latest_for("t1").status == ScanRunStatus.SUCCESS
