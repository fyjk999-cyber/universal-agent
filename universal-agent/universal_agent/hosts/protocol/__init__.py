"""hosts.protocol — the host abstraction surface."""
from __future__ import annotations

from .host import HostProtocol
from .notification import ApprovalProvider, NotificationProvider

__all__ = ["ApprovalProvider", "HostProtocol", "NotificationProvider"]
