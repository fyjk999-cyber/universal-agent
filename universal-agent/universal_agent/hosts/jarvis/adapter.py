"""MockJarvisHostAdapter（P1.6 改造）— 只发 Command，不存 Task 真相。

同 Harness adapter：Task 操作委托 TaskCoordinator（单一真相源）。
Jarvis 9 项预留能力保留声明。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ...core.contracts import WatchTask
from ...coordinator.run_once import ScanRunner, run_once
from ...coordinator.task_coordinator import TaskCoordinator, TaskCommandError
from ..deepseek_harness.adapter import _notification_fingerprint
from ..protocol import HostProtocol

log = logging.getLogger("ua.hosts.jarvis")


class MockJarvisHostAdapter(HostProtocol):
    CAPABILITIES = [
        "voice_intent", "desktop_notification", "mobile_notification",
        "approval_request", "task_status", "memory_query", "watch_query",
        "action_status", "agent_health",
    ]

    def __init__(self, data_dir: Optional[Path] = None,
                 coordinator: Optional[TaskCoordinator] = None,
                 scan_runner: Optional[ScanRunner] = None,
                 scan_runs=None,
                 notifications=None,
                 notification_sink=None,
                 approval_inbox=None,
                 task_repo=None) -> None:
        self.coordinator = coordinator
        self.scan_runner = scan_runner
        self.scan_runs = scan_runs
        self.notifications = notifications
        self.notification_sink = notification_sink
        self.approval_inbox = approval_inbox
        self.task_repo = task_repo

    # ---- HostProtocol：Task 操作委托 Command ----
    def create_task(self, task: WatchTask) -> WatchTask:
        if self.coordinator is None:
            raise TaskCommandError("no TaskCoordinator wired")
        return self.coordinator.create_watch(task)

    def update_task(self, task: WatchTask) -> WatchTask:
        """P1.1：经 Coordinator 命令（StateMachine 校验），禁止直接 repo.update。"""
        if self.coordinator is None:
            raise TaskCommandError("no TaskCoordinator wired")
        return self.coordinator.apply_update(task)

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
        """FR-030：与 Harness 适配器同契约（Host Swap 后仍可用）。"""
        if self.coordinator is None:
            raise TaskCommandError("no TaskCoordinator wired")
        if self.scan_runner is None:
            raise TaskCommandError("run_task_once: no scan runner wired (service assembly)")
        task = self.coordinator.get(task_id)
        if task is None:
            raise TaskCommandError(f"run_task_once: task not found: {task_id}")
        return run_once(task, runner=self.scan_runner, scan_runs=self.scan_runs,
                        task_repo=self.task_repo)

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
        """FR-031：与 Harness 适配器同契约（持久化 + 投递通道）。"""
        if self.notifications is not None:
            fp = notification.get("fingerprint") or _notification_fingerprint(notification)
            self.notifications.record(
                fp, str(notification.get("task_id", "")), notification)
        if self.notification_sink is not None:
            self.notification_sink(notification)
            return
        log.info("JARVIS NOTIFICATION (no sink): %s",
                 notification.get("title", notification))

    def request_approval(self, approval: Dict[str, Any]) -> Dict[str, Any]:
        """FR-032：与 Harness 适配器同契约（真实创建 + 真实决策入口）。"""
        if self.approval_inbox is None:
            raise TaskCommandError(
                "request_approval: no approval inbox wired (service assembly)")
        item = self.approval_inbox.request(
            approval_type=str(approval.get("type", "purchase")),
            title=str(approval.get("title", "approval")),
            payload=approval.get("payload"),
            task_id=str(approval.get("task_id", "")) or None)
        return {"approval_id": item["approval_id"], "status": item["status"],
                "approved": None, "title": item["title"]}

    def decide_approval(self, approval_id: str, approved: bool) -> Dict[str, Any]:
        """FR-032：用户决策入口（Host Swap 后同一契约）。"""
        if self.approval_inbox is None:
            raise TaskCommandError("decide_approval: no approval inbox wired")
        item = self.approval_inbox.decide(approval_id, approved)
        return {"approval_id": item["approval_id"], "status": item["status"],
                "approved": item["decision"]}

    def get_host_user_context(self) -> Dict[str, Any]:
        return {"host": "jarvis", "timezone": "Asia/Shanghai"}

    def publish_event(self, event: Any) -> None:
        log.debug("jarvis event bridge: %s", getattr(event, "event_type", event))
