"""SQLite 实现（P1.2）— Task 单一真相源。

Task 状态只存在于 Universal Agent 的 TaskRepository；Host 只发 Command。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import List, Optional

from ..core.contracts import WatchTask
from .protocol import TaskRepository
from .sqlite import Database


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SqliteTaskRepository(TaskRepository):
    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, task: WatchTask) -> WatchTask:
        self.db.execute(
            "INSERT OR REPLACE INTO tasks (id, data, state, next_scan_at, updated_at) "
            "VALUES (?,?,?,?,?)",
            (task.id, json.dumps(task.model_dump(mode="json"), ensure_ascii=False),
             task.state.value,
             task.next_scan_at.isoformat() if task.next_scan_at else None,
             _now()))
        return task

    def update(self, task: WatchTask) -> WatchTask:
        return self.create(task)  # upsert 语义

    def get(self, task_id: str) -> Optional[WatchTask]:
        row = self.db.query_one("SELECT data FROM tasks WHERE id=?", (task_id,))
        if row is None:
            return None
        return WatchTask.model_validate(json.loads(row["data"]))

    def list(self) -> List[WatchTask]:
        rows = self.db.query_all("SELECT data FROM tasks")
        return [WatchTask.model_validate(json.loads(r["data"])) for r in rows]

    def delete(self, task_id: str) -> bool:
        cur = self.db.execute("DELETE FROM tasks WHERE id=?", (task_id,))
        return cur.rowcount > 0

    def active_watches(self) -> List[WatchTask]:
        from ..core.state_machine import alive_states
        alive = {s.value for s in alive_states()}
        rows = self.db.query_all("SELECT data FROM tasks WHERE state IN "
                                 "(%s)" % ",".join("?" * len(alive)), tuple(alive))
        return [WatchTask.model_validate(json.loads(r["data"])) for r in rows]

    def due_tasks_utc(self, now) -> List[str]:
        from ..core.state_machine import alive_states
        alive = {s.value for s in alive_states()}
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        now = now.astimezone(timezone.utc)
        out: List[str] = []
        for task in self.active_watches():
            nxt = task.next_scan_at
            if nxt is None:
                continue
            if nxt.tzinfo is None:
                nxt = nxt.replace(tzinfo=timezone.utc)
            if nxt.astimezone(timezone.utc) <= now:
                out.append(task.id)
        return out
