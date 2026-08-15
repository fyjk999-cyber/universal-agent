"""P1.1 — 端到端验收：SQLite 唯一真相 + 多进程 lease 防双运行。

验收场景：
1. UniversalAgentService 装配（唯一 Repository Set）
2. 两个服务实例（模拟双进程）看到同一 Task 状态（SQLite 共享）
3. 双 daemon 同时 tick → 同一 task 只执行一次（RunLease DB 互斥）
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from universal_agent.coordinator.scheduler.daemon import WatchDaemon
from universal_agent.core.contracts import WatchState, WatchTask
from universal_agent.service import UniversalAgentService

WATCH_ID = "qzn-watch"


def _task() -> WatchTask:
    return WatchTask(
        id=WATCH_ID, type="watch", domain="flight",
        schedule={"timezone": "Asia/Shanghai", "baseline": ["09:00"]},
    )


def test_two_service_instances_share_task_state(tmp_path: Path) -> None:
    """两个服务实例（模拟双进程）共享同一 SQLite → 看到同一 Task 状态。"""
    svc1 = UniversalAgentService(data_dir=tmp_path / "data")
    try:
        svc1.coordinator.create_watch(_task())
        # 第二个实例（同 DB）
        svc2 = UniversalAgentService(data_dir=tmp_path / "data")
        try:
            t2 = svc2.coordinator.get(WATCH_ID)
            assert t2 is not None
            assert t2.id == WATCH_ID
            # 通过 svc1 修改 → svc2 立即可见（单一真相源）
            svc1.coordinator.activate(WATCH_ID)
            svc1.coordinator.pause(WATCH_ID)
            t2_after = svc2.coordinator.get(WATCH_ID)
            assert t2_after.state == WatchState.PAUSED
        finally:
            svc2.close()
    finally:
        svc1.close()


def test_two_daemons_same_task_runs_once(tmp_path: Path) -> None:
    """双 daemon（双进程）同时 tick：同一 task 只执行一次（lease 互斥）。"""
    from datetime import datetime, timedelta, timezone
    from universal_agent.coordinator.scheduler.runlease import RunLease

    svc1 = UniversalAgentService(data_dir=tmp_path / "data")
    svc2 = UniversalAgentService(data_dir=tmp_path / "data")
    try:
        # 两个进程共享同一 DB 与 RunLease 表
        lease = RunLease(svc1.db, default_ttl_seconds=600)
        executed: list = []

        async def runner(task: WatchTask) -> dict:
            executed.append(task.id)
            return {"ok": True}

        t = _task()
        now = datetime.now(timezone.utc)
        t.next_scan_at = now - timedelta(minutes=5)
        svc1.coordinator.create_watch(t)
        svc1.coordinator.activate(WATCH_ID)

        d1 = WatchDaemon(registry=svc1.repos.tasks, scan_runs=svc1.repos.scan_runs,
                         tick_seconds=60, runner=runner, lease=lease, lease_owner="proc-1")
        d2 = WatchDaemon(registry=svc2.repos.tasks, scan_runs=svc2.repos.scan_runs,
                         tick_seconds=60, runner=runner, lease=lease, lease_owner="proc-2")

        # 两个 daemon 同时 tick（模拟双进程竞争）
        async def run_both():
            await asyncio.gather(d1._tick(), d2._tick())

        asyncio.run(run_both())
        # lease 互斥：只有 1 次执行
        assert len(executed) == 1, f"双 daemon 同一 task 执行了 {len(executed)} 次"
    finally:
        svc1.close()
        svc2.close()


def test_restart_preserves_scanrun_and_task(tmp_path: Path) -> None:
    """重启（新服务实例）后 Task 与 ScanRun 都在（SQLite 持久）。"""
    svc1 = UniversalAgentService(data_dir=tmp_path / "data")
    try:
        svc1.coordinator.create_watch(_task())
        run = svc1.repos.scan_runs.start(WATCH_ID)
        svc1.repos.scan_runs.finish(run.run_id, "SUCCESS")
    finally:
        svc1.close()

    # 模拟重启：全新实例读同一 DB
    svc2 = UniversalAgentService(data_dir=tmp_path / "data")
    try:
        t = svc2.coordinator.get(WATCH_ID)
        assert t is not None
        runs = svc2.repos.scan_runs.list_all()
        assert len(runs) == 1
        assert runs[0].status.value == "SUCCESS"
    finally:
        svc2.close()
