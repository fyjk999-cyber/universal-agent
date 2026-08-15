"""HarnessHostAdapter（P1.6 改造）— 只发 Command，不存 Task 真相。

P4.3：Host 只做 I/O（通知/审批/上下文/事件桥）；Task 状态操作
委托 TaskCoordinator → StateMachine → TaskRepository（单一真相源）。
"""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ...core.contracts import WatchTask
from ...coordinator.run_once import ScanRunner, run_once
from ...coordinator.task_coordinator import TaskCoordinator, TaskCommandError
from ..protocol import HostProtocol

log = logging.getLogger("ua.hosts.harness")

#: 通知投递通道：Host 注册的真实接收器（DSH 插件 / 桌面 / 未来 Jarvis）
NotificationSink = Callable[[Dict[str, Any]], None]


def _notification_fingerprint(notification: Dict[str, Any]) -> str:
    """确定性通知指纹（FR-160 跨重启去重基础）。"""
    payload = {"task_id": notification.get("task_id"),
               "event_type": notification.get("event_type"),
               "title": notification.get("title"),
               "material": notification.get("material")}
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


class HarnessHostAdapter(HostProtocol):
    """Host 侧薄适配器：Task 真相在 Universal Agent（TaskCoordinator）。

    Host 保存的唯一状态：通知/审批转发（通过回调），不保存 Task。
    P23（FR-030）：`run_task_once` 通过注入的 scan_runner 真正执行一次扫描，
    并用 scan_runs 仓库记录 ScanRun（与 WatchDaemon 同语义）。
    """

    def __init__(self, data_dir: Optional[Path] = None,
                 coordinator: Optional[TaskCoordinator] = None,
                 scan_runner: Optional[ScanRunner] = None,
                 scan_runs=None,
                 notifications=None,
                 notification_sink=None,
                 approval_inbox=None) -> None:
        self.coordinator = coordinator  # 注入或由宿主装配
        self.scan_runner = scan_runner  # task → 结果摘要（可选；无则 run_task_once 显式失败）
        self.scan_runs = scan_runs      # ScanRun 仓库（可选；有则记录每次执行）
        self.notifications = notifications      # SQLite 通知仓库（FR-031 持久化，FR-160 跨重启）
        self.notification_sink = notification_sink  # 真实投递通道（可选；无则仅日志）
        self.approval_inbox = approval_inbox  # 审批箱（FR-032：真实创建 + 用户决策）

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
        """FR-030：真正执行一次扫描（不再 not_implemented）。

        需要装配 scan_runner；未装配或 task 不存在时显式失败（fail-explicit）。
        """
        if self.coordinator is None:
            raise TaskCommandError("no TaskCoordinator wired")
        if self.scan_runner is None:
            raise TaskCommandError("run_task_once: no scan runner wired (service assembly)")
        task = self.coordinator.get(task_id)
        if task is None:
            raise TaskCommandError(f"run_task_once: task not found: {task_id}")
        return run_once(task, runner=self.scan_runner, scan_runs=self.scan_runs)

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
        """FR-031：通知真实送达（持久化 + 投递通道），不是只写日志。

        - 持久化：接入 SQLite notifications 仓库（跨重启可查，FR-160 基础）
        - 投递：优先调用 notification_sink（宿主注册的真实通道）；
          未注册时降级日志（显式声明，而非静默）
        """
        if self.notifications is not None:
            fp = notification.get("fingerprint") or _notification_fingerprint(notification)
            self.notifications.record(
                fp, str(notification.get("task_id", "")), notification)
        if self.notification_sink is not None:
            self.notification_sink(notification)
            return
        log.info("HARNESS NOTIFICATION (no sink): %s",
                 notification.get("title", notification))

    def request_approval(self, approval: Dict[str, Any]) -> Dict[str, Any]:
        """FR-032：真实创建审批请求（持久化），返回真实 approval_id。

        未装配审批箱时显式失败（不静默返回固定 pending）。
        """
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
        """FR-032：用户决策入口 → APPROVED/REJECTED（持久化，供 Action Pipeline 恢复）。"""
        if self.approval_inbox is None:
            raise TaskCommandError("decide_approval: no approval inbox wired")
        item = self.approval_inbox.decide(approval_id, approved)
        return {"approval_id": item["approval_id"], "status": item["status"],
                "approved": item["decision"]}

    def get_host_user_context(self) -> Dict[str, Any]:
        return {"host": "deepseek_harness", "timezone": "Asia/Shanghai"}

    def publish_event(self, event: Any) -> None:
        log.debug("harness event bridge: %s", getattr(event, "event_type", event))
