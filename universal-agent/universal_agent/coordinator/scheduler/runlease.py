"""RunLease（P1.1）— DB-backed 运行租约，多进程防同一 Task 双运行。

RunningTaskGuard 只在单进程内有效；RunLease 把租约状态放进 SQLite，
多个进程（Harness / Scheduler / 未来 Jarvis）共享同一 DB 时天然互斥。

字段（run_leases 表）：
  task_id            — 被租约保护的 task
  lease_owner        — 持有者标识（host/process）
  lease_token        — 随机 token，释放/续约须匹配（防误释放他人租约）
  acquired_at        — 获取时间
  heartbeat_at       — 最近心跳
  lease_expires_at   — 过期时间；过期后其他 owner 可 recover

语义：
  acquire            — 无租约或已过期 → 获取并返回 token；否则 None
  renew              — 持有者续约（须 token 匹配）
  release            — 持有者释放（须 token 匹配）
  recover_expired    — 收回所有过期租约，返回被回收的 task_id 列表
  is_owned           — 查询当前持有者是否为给定 owner+token
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from ...persistence.sqlite import Database


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


class RunLease:
    def __init__(self, db: Database, default_ttl_seconds: int = 600) -> None:
        self.db = db
        self.default_ttl = timedelta(seconds=default_ttl_seconds)

    def acquire(self, task_id: str, owner: str, ttl: Optional[timedelta] = None,
                token: Optional[str] = None) -> Optional[str]:
        """获取 task 的租约。成功返回 token；被他人持有返回 None。"""
        ttl = ttl or self.default_ttl
        now = _now()
        expires = now + ttl
        tok = token or secrets.token_hex(16)
        # 原子性：INSERT 冲突（已存在租约）→ 检查是否过期
        try:
            self.db.execute(
                "INSERT INTO run_leases "
                "(task_id, lease_owner, lease_token, acquired_at, heartbeat_at, lease_expires_at) "
                "VALUES (?,?,?,?,?,?)",
                (task_id, owner, tok, _iso(now), _iso(now), _iso(expires)))
            return tok
        except Exception:  # noqa: BLE001 — 已存在租约（PRIMARY KEY 冲突）
            row = self.db.query_one(
                "SELECT lease_expires_at FROM run_leases WHERE task_id=?", (task_id,))
            if row is None:
                return None
            exp = datetime.fromisoformat(row["lease_expires_at"])
            if exp <= now:
                # 过期 → 抢占（recover 语义：过期即失效）
                self.db.execute(
                    "UPDATE run_leases SET lease_owner=?, lease_token=?, acquired_at=?, "
                    "heartbeat_at=?, lease_expires_at=? WHERE task_id=? AND lease_expires_at<=?",
                    (owner, tok, _iso(now), _iso(now), _iso(expires), task_id, _iso(now)))
                still = self.db.query_one(
                    "SELECT lease_token FROM run_leases WHERE task_id=?", (task_id,))
                return tok if still is not None and still["lease_token"] == tok else None
            return None

    def renew(self, task_id: str, owner: str, token: str,
              ttl: Optional[timedelta] = None) -> bool:
        """持有者续约。token 不匹配 → False。"""
        ttl = ttl or self.default_ttl
        now = _now()
        expires = now + ttl
        cur = self.db.execute(
            "UPDATE run_leases SET heartbeat_at=?, lease_expires_at=? "
            "WHERE task_id=? AND lease_owner=? AND lease_token=?",
            (_iso(now), _iso(expires), task_id, owner, token))
        return cur.rowcount > 0

    def release(self, task_id: str, owner: str, token: str) -> bool:
        """持有者释放。token 不匹配 → False（不误删他人租约）。"""
        cur = self.db.execute(
            "DELETE FROM run_leases WHERE task_id=? AND lease_owner=? AND lease_token=?",
            (task_id, owner, token))
        return cur.rowcount > 0

    def recover_expired(self, now: Optional[datetime] = None) -> List[str]:
        """收回所有过期租约，返回被回收的 task_id 列表。"""
        now = now or _now()
        rows = self.db.query_all(
            "SELECT task_id FROM run_leases WHERE lease_expires_at<=?", (_iso(now),))
        ids = [r["task_id"] for r in rows]
        for tid in ids:
            self.db.execute("DELETE FROM run_leases WHERE task_id=?", (tid,))
        return ids

    def is_owned(self, task_id: str, owner: str, token: str) -> bool:
        row = self.db.query_one(
            "SELECT lease_owner, lease_token FROM run_leases WHERE task_id=?", (task_id,))
        return row is not None and row["lease_owner"] == owner and row["lease_token"] == token

    def holder(self, task_id: str) -> Optional[str]:
        row = self.db.query_one(
            "SELECT lease_owner FROM run_leases WHERE task_id=?", (task_id,))
        return row["lease_owner"] if row else None
