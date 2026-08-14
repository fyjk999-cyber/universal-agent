"""Event bridge for the Jarvis host (mock in Phase 1)."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from ...core.contracts import new_id
from ...events import EventBusProtocol, EventEnvelope, EventType

log = logging.getLogger("ua.hosts.jarvis.bridge")


class JarvisEventBridge:
    def __init__(self, bus: EventBusProtocol, source: str = "jarvis") -> None:
        self.bus = bus
        self.source = source

    async def publish(self, event_type: EventType, payload: Dict[str, Any],
                      task_id: Optional[str] = None, trace_id: Optional[str] = None) -> EventEnvelope:
        envelope = EventEnvelope(
            event_type=event_type,
            trace_id=trace_id or new_id("trace"),
            task_id=task_id,
            source=self.source,
            payload=payload,
        )
        await self.bus.publish(envelope)
        return envelope
