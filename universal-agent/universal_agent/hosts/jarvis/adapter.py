"""MockJarvisHostAdapter — proves host swap requires ZERO Core changes (§46, §73).

Same persistence contract as HarnessHostAdapter, same HostProtocol.
Core code is untouched when swapping Harness → Jarvis.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...core.contracts import WatchState, WatchTask
from ...core.state_machine import transition
from ..protocol import HostProtocol

log = logging.getLogger("ua.hosts.jarvis")


class MockJarvisHostAdapter(HostProtocol):
    """Phase 1 mock: JSON-file persistence mirroring the Harness adapter.

    Jarvis-specific reserved capabilities (§11) are declared but unused in mock:
      voice_intent / desktop_notification / mobile_notification / approval_request
      / task_status / memory_query / watch_query / action_status / agent_health
    """

    CAPABILITIES = [
        "voice_intent", "desktop_notification", "mobile_notification",
        "approval_request", "task_status", "memory_query", "watch_query",
        "action_status", "agent_health",
    ]

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._tasks_file = self.data_dir / "tasks.json"
        self._tasks: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if self._tasks_file.exists():
            try:
                self._tasks = json.loads(self._tasks_file.read_text("utf-8"))
            except json.JSONDecodeError:
                log.warning("tasks.json corrupt; starting empty")

    def _save(self) -> None:
        self._tasks_file.write_text(json.dumps(self._tasks, ensure_ascii=False, indent=2), "utf-8")

    def _put(self, task: WatchTask) -> WatchTask:
        self._tasks[task.id] = task.model_dump(mode="json")
        self._save()
        return task

    # ---- HostProtocol ----
    def create_task(self, task: WatchTask) -> WatchTask:
        return self._put(task)

    def update_task(self, task: WatchTask) -> WatchTask:
        return self._put(task)

    def pause_task(self, task_id: str) -> WatchTask:
        task = self.get_task(task_id)
        if task is None:
            raise KeyError(f"task not found: {task_id}")
        task.state = transition(task.state, WatchState.PAUSED)
        task.version += 1
        return self._put(task)

    def resume_task(self, task_id: str) -> WatchTask:
        task = self.get_task(task_id)
        if task is None:
            raise KeyError(f"task not found: {task_id}")
        # PAUSED → WATCHING; any other state stays as-is (no-op)
        if task.state == WatchState.PAUSED:
            task.state = transition(task.state, WatchState.WATCHING)
            task.version += 1
        return self._put(task)

    def cancel_task(self, task_id: str) -> WatchTask:
        task = self.get_task(task_id)
        if task is None:
            raise KeyError(f"task not found: {task_id}")
        task.state = transition(task.state, WatchState.CANCELLED)
        task.version += 1
        return self._put(task)

    def run_task_once(self, task_id: str) -> Dict[str, Any]:
        return {"task_id": task_id, "status": "not_implemented"}

    def list_tasks(self) -> List[WatchTask]:
        return [WatchTask.model_validate(v) for v in self._tasks.values()]

    def get_task(self, task_id: str) -> Optional[WatchTask]:
        raw = self._tasks.get(task_id)
        return WatchTask.model_validate(raw) if raw is not None else None

    def send_notification(self, notification: Dict[str, Any]) -> None:
        log.info("JARVIS NOTIFICATION: %s", notification.get("title", notification))

    def request_approval(self, approval: Dict[str, Any]) -> Dict[str, Any]:
        log.info("JARVIS APPROVAL REQUEST: %s", approval.get("title", approval))
        return {"approved": False, "status": "pending"}

    def get_host_user_context(self) -> Dict[str, Any]:
        return {"host": "jarvis", "timezone": "Asia/Shanghai"}

    def publish_event(self, event: Any) -> None:
        log.debug("jarvis event bridge: %s", getattr(event, "event_type", event))
