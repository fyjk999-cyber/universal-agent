"""HostProtocol — the ONLY surface Core may call (§9).

Core never calls Harness APIs or any other host's APIs directly.
A new host (Jarvis) is added by implementing this protocol — zero Core changes.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from ...core.contracts import WatchTask


class HostProtocol(ABC):
    """All host capabilities Core depends on.

    RULE 1/2: Core → HostProtocol ← HostAdapter.
    """

    @abstractmethod
    def create_task(self, task: WatchTask) -> WatchTask:
        """Persist a new task."""

    @abstractmethod
    def update_task(self, task: WatchTask) -> WatchTask:
        """Persist an updated task."""

    @abstractmethod
    def pause_task(self, task_id: str) -> WatchTask:
        """Pause a task."""

    @abstractmethod
    def resume_task(self, task_id: str) -> WatchTask:
        """Resume a task."""

    @abstractmethod
    def cancel_task(self, task_id: str) -> WatchTask:
        """Cancel a task."""

    @abstractmethod
    def run_task_once(self, task_id: str) -> Dict[str, Any]:
        """Run one scan cycle immediately and return a result summary."""

    @abstractmethod
    def list_tasks(self) -> List[WatchTask]:
        """List all tasks."""

    @abstractmethod
    def get_task(self, task_id: str) -> Optional[WatchTask]:
        """Get one task."""

    @abstractmethod
    def send_notification(self, notification: Dict[str, Any]) -> None:
        """Deliver a notification to the user through the host."""

    @abstractmethod
    def request_approval(self, approval: Dict[str, Any]) -> Dict[str, Any]:
        """Request human approval; returns approval decision."""

    @abstractmethod
    def get_host_user_context(self) -> Dict[str, Any]:
        """Return host/user context (e.g. timezone, user id)."""

    @abstractmethod
    def publish_event(self, event: Any) -> None:
        """Publish an event out of Core (e.g. into host's event system)."""
