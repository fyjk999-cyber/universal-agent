"""P1.1d — UniversalAgentService 聚合 + WatchDaemon 接入 RunLease。

验收：
1. UniversalAgentService 提供统一 Repository Set（SQLite 唯一真相）
2. WatchDaemon 支持 RunLease：DB 级防双运行（多进程场景）
3. 双 daemon 实例（模拟双进程）同一 task 只有一个能执行
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from universal_agent.coordinator.scheduler.runlease import RunLease
from universal_agent.core.contracts import WatchTask
from universal_agent.persistence import Database

TASKS_DIR = Path(__file__).resolve().parent.parent.parent / "tasks"
WATCH_ID = "queenstown-travel-watch"


def _task() -> WatchTask:
    return WatchTask(
        id=WATCH_ID, type="watch", domain="flight",
        schedule={"timezone": "Asia/Shanghai", "baseline": ["09:00"]},
    )


def test_universal_service_aggregates_repositories(tmp_path: Path) -> None:
    """UniversalAgentService 提供统一 Repository Set（SQLite 唯一真相）。"""
    from universal_agent.service import UniversalAgentService
    svc = UniversalAgentService(data_dir=tmp_path / "data")
    try:
        # 创建任务 → 走 TaskCoordinator
        t = _task()
        created = svc.coordinator.create_watch(t)
        assert created.state.value == "DRAFT"
        # Repository Set 都指向同一 DB
        got = svc.repos.tasks.get(WATCH_ID)
        assert got is not None and got.id == WATCH_ID
        # 主机 adapter 装配
        assert svc.adapter is not None
        listed = svc.adapter.list_tasks()
        assert any(x.id == WATCH_ID for x in listed)
    finally:
        svc.close()


def test_daemon_with_lease_prevents_second_process(tmp_path: Path) -> None:
    """双 daemon（模拟双进程）同一 task 只有一个能执行（RunLease DB 互斥）。"""
    from universal_agent.coordinator.scheduler.daemon import WatchDaemon
    from universal_agent.persistence import SqliteTaskRepository, SqliteScanRunRepository
    from universal_agent.coordinator.scheduler.runlease import RunLease

    db = Database(tmp_path / "ua.db")
    repo = SqliteTaskRepository(db)
    runs = SqliteScanRunRepository(db)
    lease = RunLease(db, default_ttl_seconds=600)
    repo.create(_task())

    executed: list = []

    async def runner(task: WatchTask) -> dict:
        executed.append(task.id)
        return {"ok": True}

    # daemon1 先启动并持有 lease
    d1 = WatchDaemon(registry=repo, scan_runs=runs, tick_seconds=60, runner=runner,
                     lease=lease, lease_owner="daemon-1")
    d1.lease_token = lease.acquire(WATCH_ID, owner="daemon-1")
    assert d1.lease_token is not None

    # daemon2 尝试获取同一 task lease → 失败
    d2 = WatchDaemon(registry=repo, scan_runs=runs, tick_seconds=60, runner=runner,
                     lease=lease, lease_owner="daemon-2")
    assert lease.acquire(WATCH_ID, owner="daemon-2") is None

    # daemon1 执行一次（持有 lease）
    asyncio.run(d1._run_task(repo.get(WATCH_ID)))
    assert len(executed) == 1
    db.close()


def test_daemon_release_lease_after_run(tmp_path: Path) -> None:
    """daemon 运行结束释放 lease → 其他实例可获取。"""
    from universal_agent.coordinator.scheduler.daemon import WatchDaemon
    from universal_agent.persistence import SqliteTaskRepository, SqliteScanRunRepository

    db = Database(tmp_path / "ua.db")
    repo = SqliteTaskRepository(db)
    runs = SqliteScanRunRepository(db)
    lease = RunLease(db)
    repo.create(_task())

    async def runner(task: WatchTask) -> dict:
        return {"ok": True}

    d = WatchDaemon(registry=repo, scan_runs=runs, tick_seconds=60, runner=runner,
                    lease=lease, lease_owner="daemon-1")
    token = lease.acquire(WATCH_ID, owner="daemon-1")
    d.lease_token = token
    asyncio.run(d._run_task(repo.get(WATCH_ID)))
    d._release_lease(WATCH_ID)
    assert lease.acquire(WATCH_ID, owner="daemon-2") is not None
    db.close()
