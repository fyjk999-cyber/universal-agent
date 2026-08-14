"""MockJarvisHostAdapter（P1.6 改造）— 只发 Command，不存 Task 真相。

同 Harness adapter：Task 操作委托 TaskCoordinator（单一真相源）。
Jarvis 9 项预留能力保留声明。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...core.contracts import WatchTask
from ...coordinator.task_coordinator import TaskCoordinator, TaskCommandError
from ..protocol import HostProtocol

log = logging.getLogger("ua.hosts.jarvis")


class MockJarvisHostAdapter(HostProtocol):
    CAPABILITIES = [
        "voice_intent", "desktop_notification", "mobile_notification",
        "approval_request", "task_status", "memory_query", "watch_query",
        "action_status", "agent_health",
    ]

    def __init__(self, data_dir: Optional[Path] = None,
                 coordinator: Optional[TaskCoordinator] = None) -> None:
        self.coordinator = coordinator

    # ---- HostProtocol：Task 操作委托 Command ----
    def create_task(self, task: WatchTask) -> WatchTask:
        if self.coordinator is None:
            raise TaskCommandError("no TaskCoordinator wired")
        return self.coordinator.create_watch(task)

    def update_task(self, task: WatchTask) -> WatchTask:
        if self.coordinator is None:
            raise TaskCommandError("no TaskCoordinator wired")
        return self.coordinator.repo.update(task)

    def pause_task(self, task_id: str) -> WatchTask:
        if self.coordinator is None:
            raise TaskCommandError("no TaskCoordinator wired")
        return self.coordinator.pause(task_id)

    def resume_task(self, task_id: str) -> WatchTask:
        if self.coordinator is None:
            raise TaskCommandError("no TaskCoordinator wired")
        return self.coordinator.resume(task_id)

    def cancel_task(self, task_id: str) -> WatchTask:
        if self.coordinator is None:
            raise TaskCommandError("no TaskCoordinator wired")
        return self.coordinator.cancel(task_id)

    def run_task_once(self, task_id: str) -> Dict[str, Any]:
        return {"task_id": task_id, "status": "not_implemented"}

    def list_tasks(self) -> List[WatchTask]:
        if self.coordinator is None:
            return []
        return self.coordinator.list()

    def get_task(self, task_id: str) -> Optional[WatchTask]:
        if self.coordinator is None:
            return None
        return self.coordinator.get(task_id)

    # ---- Host I/O ----
    def send_notification(self, notification: Dict[str, Any]) -> None:
        log.info("JARVIS NOTIFICATION: %s", notification.get("title", notification))

    def request_approval(self, approval: Dict[str, Any]) -> Dict[str, Any]:
        log.info("JARVIS APPROVAL REQUEST: %s", approval.get("title", approval))
        return {"approved": False, "status": "pending"}

    def get_host_user_context(self) -> Dict[str, Any]:
        return {"host": "jarvis", "timezone": "Asia/Shanghai"}

    def publish_event(self, event: Any) -> None:
        log.debug("jarvis event bridge: %s", getattr(event, "event_type", event))
