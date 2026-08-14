"""Watch Manager — drives WatchTask lifecycle transitions (§14, §69).

Phase 1 skeleton: create → activate → watching; emits WATCH_STARTED /
WATCH_PAUSED / WATCH_RESUMED / WATCH_EXPIRED events. Scan execution itself is
wired in Phase 2 (the manager only manages state + schedules).
"""
from __future__ import annotations

import logging
from typing import List, Optional

from ...core.contracts import WatchState, WatchTask, new_id, utc_now
from ...core.state_machine import TransitionError, transition
from ...events import EventBusProtocol, EventEnvelope, EventType
from ..scheduler import BaselineScheduler, NextRun
from ..task_registry import TaskRegistry

log = logging.getLogger("ua.coordinator.watch_manager")


class WatchManager:
    def __init__(self, registry: TaskRegistry, bus: EventBusProtocol,
                 scheduler: Optional[BaselineScheduler] = None) -> None:
        self.registry = registry
        self.bus = bus
        self.scheduler = scheduler or BaselineScheduler()

    # ---- lifecycle ----
    def create_watch(self, task: WatchTask) -> WatchTask:
        """Persist a DRAFT watch."""
        task.state = WatchState.DRAFT
        return self.registry.create(task)

    def activate(self, task_id: str) -> WatchTask:
        task = self._get(task_id)
        self._apply(task, WatchState.ACTIVE)
        self._schedule_next(task)
        self._emit(task, EventType.WATCH_STARTED)
        return self.registry.update(task)

    def start_watching(self, task_id: str) -> WatchTask:
        task = self._get(task_id)
        self._apply(task, WatchState.WATCHING)
        return self.registry.update(task)

    def pause(self, task_id: str) -> WatchTask:
        task = self._get(task_id)
        self._apply(task, WatchState.PAUSED)
        task.next_scan_at = None
        self._emit(task, EventType.WATCH_PAUSED)
        return self.registry.update(task)

    def resume(self, task_id: str) -> WatchTask:
        task = self._get(task_id)
        self._apply(task, WatchState.WATCHING)
        self._schedule_next(task)
        self._emit(task, EventType.WATCH_RESUMED)
        return self.registry.update(task)

    def expire(self, task_id: str) -> WatchTask:
        task = self._get(task_id)
        self._apply(task, WatchState.EXPIRED)
        self._emit(task, EventType.WATCH_EXPIRED)
        return self.registry.update(task)

    def fail(self, task_id: str, reason: str = "") -> WatchTask:
        task = self._get(task_id)
        self._apply(task, WatchState.FAILED)
        task.history.append({"at": utc_now().isoformat(), "event": "FAILED", "reason": reason})
        return self.registry.update(task)

    # ---- scheduling ----
    def _schedule_next(self, task: WatchTask) -> None:
        run: Optional[NextRun] = self.scheduler.next_run(task)
        task.next_scan_at = run.at if run else None

    def mark_scanned(self, task_id: str) -> WatchTask:
        """Record a completed scan tick; roll next_scan_at forward."""
        task = self._get(task_id)
        task.scan_count += 1
        task.last_scan_at = utc_now()
        self._schedule_next(task)
        return self.registry.update(task)

    def due_tasks(self, now_str: str) -> List[WatchTask]:
        return self.registry.due_tasks(now_str)

    # ---- helpers ----
    def _get(self, task_id: str) -> WatchTask:
        task = self.registry.get(task_id)
        if task is None:
            raise KeyError(f"task not found: {task_id}")
        return task

    @staticmethod
    def _apply(task: WatchTask, target: WatchState) -> None:
        try:
            new_state = transition(task.state, target)
        except TransitionError as exc:
            raise TransitionError(task.state, target) from exc
        task.state = new_state
        task.version += 1
        task.updated_at = utc_now()
        task.history.append({"at": utc_now().isoformat(), "event": target.value})

    def _emit(self, task: WatchTask, event_type: EventType) -> None:
        import asyncio
        envelope = EventEnvelope(
            event_type=event_type,
            trace_id=new_id("trace"),
            task_id=task.id,
            source="watch_manager",
            payload={"task_id": task.id, "state": task.state.value},
        )
        try:
            asyncio.get_running_loop().create_task(self.bus.publish(envelope))
        except RuntimeError:
            log.warning("no running loop; event not emitted: %s", event_type.value)
