"""Event bridge between Harness and the Universal Agent EventBus.

Phase 1 skeleton: forwards HostProtocol.publish_event payloads onto the
in-process bus, wrapped in a valid EventEnvelope.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from ...core.contracts import new_id
from ...events import EventBusProtocol, EventEnvelope, EventType

log = logging.getLogger("ua.hosts.harness.bridge")


class HarnessEventBridge:
    def __init__(self, bus: EventBusProtocol, source: str = "deepseek_harness") -> None:
        self.bus = bus
        self.source = source

    async def publish(self, event_type: EventType, payload: Dict[str, Any],
                      task_id: Optional[str] = None, trace_id: Optional[str] = None) -> None:
        envelope = EventEnvelope(
            event_type=event_type,
            trace_id=trace_id or new_id("trace"),
            task_id=task_id,
            source=self.source,
            payload=payload,
        )
        await self.bus.publish(envelope)
        return envelope

    async def forward(self, raw: Any) -> None:
        """Adapt an arbitrary host event object into an envelope (skeleton)."""
        event_type = getattr(raw, "event_type", None)
        if event_type is None:
            log.warning("cannot forward event without event_type: %r", raw)
            return
        await self.publish(
            EventType(event_type),
            payload=getattr(raw, "payload", {}) or {},
            task_id=getattr(raw, "task_id", None),
            trace_id=getattr(raw, "trace_id", None),
        )
