"""Task Registry — Core-owned registry of WatchTasks (§15).

Phase 1: in-memory + JSON persistence (host-independent). The host adapter
also persists tasks, but the registry is the Core's source of truth for
runtime scheduling state.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from ...core.contracts import WatchTask

log = logging.getLogger("ua.coordinator.task_registry")


class TaskRegistry:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._file = self.data_dir / "task_registry.json"
        self._tasks: Dict[str, WatchTask] = {}
        self._load()

    def _load(self) -> None:
        if self._file.exists():
            try:
                raw = json.loads(self._file.read_text("utf-8"))
                self._tasks = {k: WatchTask.model_validate(v) for k, v in raw.items()}
            except Exception:  # noqa: BLE001
                log.warning("task_registry.json corrupt; starting empty")

    def _save(self) -> None:
        self._file.write_text(
            json.dumps({k: v.model_dump(mode="json") for k, v in self._tasks.items()},
                       ensure_ascii=False, indent=2), "utf-8")

    # ---- CRUD ----
    def create(self, task: WatchTask) -> WatchTask:
        self._tasks[task.id] = task
        self._save()
        return task

    def update(self, task: WatchTask) -> WatchTask:
        if task.id not in self._tasks:
            raise KeyError(f"task not found: {task.id}")
        self._tasks[task.id] = task
        self._save()
        return task

    def get(self, task_id: str) -> Optional[WatchTask]:
        return self._tasks.get(task_id)

    def list(self) -> List[WatchTask]:
        return list(self._tasks.values())

    def delete(self, task_id: str) -> bool:
        if task_id in self._tasks:
            del self._tasks[task_id]
            self._save()
            return True
        return False

    # ---- scheduling helpers ----
    def active_watches(self) -> List[WatchTask]:
        from ...core.state_machine import alive_states
        return [t for t in self._tasks.values() if t.state in alive_states()]

    def due_tasks_utc(self, now: "datetime", max_lookback: int = 0) -> List[str]:
        """P0.1/P0.9-7: 用 datetime 比较判定到期（task.next_scan_at <= now_utc）。

        返回到期 task id 列表。`max_lookback` > 0 时允许补跑最多 N 个
        错过的扫描窗口（配合 misfire RUN_ONCE/CATCH_UP_LIMITED）。
        """
        from datetime import timezone
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        now = now.astimezone(timezone.utc)
        out: List[str] = []
        for t in self.active_watches():
            nxt = t.next_scan_at
            if nxt is None:
                continue
            if nxt.tzinfo is None:
                nxt = nxt.replace(tzinfo=timezone.utc)
            nxt = nxt.astimezone(timezone.utc)
            if nxt <= now:
                out.append(t.id)
        return out
