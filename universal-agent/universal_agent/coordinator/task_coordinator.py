"""TaskCoordinator（P1.2/P4.3）— Task 唯一状态修改入口。

Host 只发 Command（Create/Pause/Resume/Cancel），由本协调器
→ StateMachine → TaskRepository 完成修改。Host 不保存 Task 真相。
"""
from __future__ import annotations

from typing import List, Optional

from ..core.contracts import WatchState, WatchTask
from ..core.state_machine import TransitionError, transition
from ..events import EventBusProtocol, EventEnvelope, EventType, InProcessEventBus
from ..persistence import Database, SqliteTaskRepository
from ..persistence.protocol import TaskRepository


class TaskCommandError(RuntimeError):
    pass


class TaskCoordinator:
    def __init__(self, repo: TaskRepository,
                 bus: Optional[EventBusProtocol] = None) -> None:
        self.repo = repo
        self.bus = bus or InProcessEventBus()

    # ---- Commands（Host 可调）----
    def create_watch(self, task: WatchTask) -> WatchTask:
        task.state = WatchState.DRAFT
        created = self.repo.create(task)
        self._emit(EventType.TASK_CREATED, created)
        return created

    def activate(self, task_id: str) -> WatchTask:
        task = self._get(task_id)
        task.state = transition(task.state, WatchState.ACTIVE)
        task.version += 1
        updated = self.repo.update(task)
        self._emit(EventType.TASK_UPDATED, updated)
        return updated

    def pause(self, task_id: str) -> WatchTask:
        task = self._get(task_id)
        task.state = transition(task.state, WatchState.PAUSED)
        task.version += 1
        updated = self.repo.update(task)
        self._emit(EventType.WATCH_PAUSED, updated)
        return updated

    def resume(self, task_id: str) -> WatchTask:
        task = self._get(task_id)
        if task.state == WatchState.PAUSED:
            task.state = transition(task.state, WatchState.WATCHING)
        elif task.state == WatchState.DRAFT:
            task.state = transition(task.state, WatchState.ACTIVE)
        task.version += 1
        updated = self.repo.update(task)
        self._emit(EventType.WATCH_RESUMED, updated)
        return updated

    def cancel(self, task_id: str) -> WatchTask:
        task = self._get(task_id)
        task.state = transition(task.state, WatchState.CANCELLED)
        task.version += 1
        updated = self.repo.update(task)
        self._emit(EventType.TASK_UPDATED, updated)
        return updated

    # ---- Queries（只读，不修改状态）----
    def get(self, task_id: str) -> Optional[WatchTask]:
        return self.repo.get(task_id)

    def list(self) -> List[WatchTask]:
        return self.repo.list()

    def _get(self, task_id: str) -> WatchTask:
        task = self.repo.get(task_id)
        if task is None:
            raise TaskCommandError(f"task not found: {task_id}")
        return task

    def _emit(self, event_type: EventType, task: WatchTask) -> None:
        import asyncio
        envelope = EventEnvelope(
            event_type=event_type, trace_id=f"trc_{task.id}",
            task_id=task.id, source="task_coordinator",
            payload={"task_id": task.id, "state": task.state.value})
        try:
            asyncio.get_running_loop().create_task(self.bus.publish(envelope))
        except RuntimeError:
            pass


def sqlite_task_coordinator(path: str | Path, **kw) -> TaskCoordinator:
    from pathlib import Path as _P
    db = Database(_P(path) if isinstance(path, str) else path)
    return TaskCoordinator(SqliteTaskRepository(db), **kw)
