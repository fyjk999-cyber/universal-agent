"""events package — Event contract surface."""
from __future__ import annotations

from .bus import InProcessEventBus
from .envelope import EventEnvelope
from .protocol import EventBusProtocol, EventHandler
from .reliable import OutboxDispatcher
from .types import EventType

__all__ = [
    "EventBusProtocol",
    "EventEnvelope",
    "EventHandler",
    "EventType",
    "InProcessEventBus",
    "OutboxDispatcher",
]
