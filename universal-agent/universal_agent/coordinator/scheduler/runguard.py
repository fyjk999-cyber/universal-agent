"""RunningTaskGuard（P0.9-1）— 防同一 task 双启动 ScanRun。

WatchDaemon 中：一个 task 在同一时间只能有一个 RUNNING ScanRun。
retry 与 baseline 不得同时启动同一 task。
"""
from __future__ import annotations

import threading
from typing import Optional, Set


class RunningTaskGuard:
    """进程内运行守卫：跟踪 RUNNING 的 task_id。"""

    def __init__(self) -> None:
        self._running: Set[str] = set()
        self._lock = threading.Lock()

    def try_acquire(self, task_id: str) -> bool:
        """尝试占用 task_id；已在运行则返回 False。"""
        with self._lock:
            if task_id in self._running:
                return False
            self._running.add(task_id)
            return True

    def release(self, task_id: str) -> None:
        with self._lock:
            self._running.discard(task_id)

    def is_running(self, task_id: str) -> bool:
        with self._lock:
            return task_id in self._running

    def running_tasks(self) -> Set[str]:
        with self._lock:
            return set(self._running)
