"""HarnessHostAdapter（P1.6 改造）— 只发 Command，不存 Task 真相。

P4.3：Host 只做 I/O（通知/审批/上下文/事件桥）；Task 状态操作
委托 TaskCoordinator → StateMachine → TaskRepository（单一真相源）。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...core.contracts import WatchTask
from ...coordinator.task_coordinator import TaskCoordinator, TaskCommandError
from ..protocol import HostProtocol

log = logging.getLogger("ua.hosts.harness")


class HarnessHostAdapter(HostProtocol):
    """Host 侧薄适配器：Task 真相在 Universal Agent（TaskCoordinator）。

    Host 保存的唯一状态：通知/审批转发（通过回调），不保存 Task。
    """

    def __init__(self, data_dir: Optional[Path] = None,
                 coordinator: Optional[TaskCoordinator] = None) -> None:
        self.coordinator = coordinator  # 注入或由宿主装配

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
        return {"task_id": task_id, "status": "not_implemented"}

    def list_tasks(self) -> List[WatchTask]:
        if self.coordinator is None:
            return []
        return self.coordinator.list()

    def get_task(self, task_id: str) -> Optional[WatchTask]:
        if self.coordinator is None:
            return None
        return self.coordinator.get(task_id)

    # ---- Host I/O（P4.3：Host 只做 I/O）----
    def send_notification(self, notification: Dict[str, Any]) -> None:
        log.info("HARNESS NOTIFICATION: %s", notification.get("title", notification))

    def request_approval(self, approval: Dict[str, Any]) -> Dict[str, Any]:
        log.info("HARNESS APPROVAL REQUEST: %s", approval.get("title", approval))
        return {"approved": False, "status": "pending"}

    def get_host_user_context(self) -> Dict[str, Any]:
        return {"host": "deepseek_harness", "timezone": "Asia/Shanghai"}

    def publish_event(self, event: Any) -> None:
        log.debug("harness event bridge: %s", getattr(event, "event_type", event))
