"""Notification + Approval protocol sub-contracts (§8)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict


class NotificationProvider(ABC):
    @abstractmethod
    def send(self, notification: Dict[str, Any]) -> None:
        """Send a notification (channel decided by host)."""


class ApprovalProvider(ABC):
    @abstractmethod
    def request(self, approval: Dict[str, Any]) -> Dict[str, Any]:
        """Request human approval. Return {'approved': bool, ...}."""
