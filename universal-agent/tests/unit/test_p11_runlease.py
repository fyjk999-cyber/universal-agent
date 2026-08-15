"""P1.1 — RunLease（DB-backed）测试：多进程/多实例防同一 Task 双运行。

先写失败测试（RED），再实现（GREEN）。
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from universal_agent.persistence import Database
from universal_agent.coordinator.scheduler.runlease import RunLease


@pytest.fixture()
def db(tmp_path: Path) -> Database:
    return Database(tmp_path / "test.db")


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


def _task_id(n: int = 1) -> str:
    return f"task_{n}"


def test_acquire_returns_token_and_owns(db: Database) -> None:
    lease = RunLease(db)
    token = lease.acquire(_task_id(), owner="harness-1")
    assert token is not None
    assert lease.is_owned(_task_id(), owner="harness-1", token=token)


def test_second_owner_cannot_acquire_while_held(db: Database) -> None:
    lease = RunLease(db)
    token = lease.acquire(_task_id(), owner="harness-1")
    assert token is not None
    # 第二个进程/实例尝试获取同一 task → 失败
    assert lease.acquire(_task_id(), owner="scheduler-2") is None


def test_release_frees_lease(db: Database) -> None:
    lease = RunLease(db)
    token = lease.acquire(_task_id(), owner="harness-1")
    assert token is not None
    assert lease.release(_task_id(), owner="harness-1", token=token) is True
    # 释放后可重新获取
    assert lease.acquire(_task_id(), owner="harness-2") is not None


def test_renew_keeps_lease_alive(db: Database) -> None:
    lease = RunLease(db, default_ttl_seconds=2)
    token = lease.acquire(_task_id(), owner="harness-1")
    assert token is not None
    assert lease.renew(_task_id(), owner="harness-1", token=token) is True


def test_recover_expired_reclaims_lease(db: Database) -> None:
    lease = RunLease(db, default_ttl_seconds=1)
    token = lease.acquire(_task_id(), owner="crashed-owner")
    assert token is not None
    # 过期后（模拟崩溃遗留）→ 新 owner 可恢复
    time.sleep(1.2)
    recovered = lease.recover_expired(now=None)
    assert _task_id() in recovered
    new_token = lease.acquire(_task_id(), owner="harness-2")
    assert new_token is not None


def test_lease_persists_across_instances(db: Database) -> None:
    """同一 DB 文件、两个 RunLease 实例（模拟两个进程）→ 互斥。"""
    lease1 = RunLease(db)
    token = lease1.acquire(_task_id(), owner="proc-1")
    assert token is not None
    lease2 = RunLease(db)
    assert lease2.acquire(_task_id(), owner="proc-2") is None


def test_lease_prevents_concurrent_execution(db_path: Path) -> None:
    """并发获取同一 task：只有一个成功（多进程模拟：各自独立 DB 连接）。"""
    results: list = []
    lock = threading.Lock()

    def worker(owner: str) -> None:
        d = Database(db_path)
        lease = RunLease(d)
        tok = lease.acquire(_task_id(), owner=owner)
        with lock:
            results.append((owner, tok))
        d.close()

    threads = [threading.Thread(target=worker, args=(f"w{i}",)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    got = [o for o, tok in results if tok is not None]
    assert len(got) == 1


def test_lease_expiry_metadata(db: Database) -> None:
    lease = RunLease(db, default_ttl_seconds=60)
    token = lease.acquire(_task_id(), owner="h1")
    assert token is not None
    row = db.query_one(
        "SELECT lease_owner, lease_token, lease_expires_at FROM run_leases WHERE task_id=?",
        (_task_id(),))
    assert row is not None
    assert row["lease_owner"] == "h1"
    assert row["lease_token"] == token
    assert row["lease_expires_at"] is not None
