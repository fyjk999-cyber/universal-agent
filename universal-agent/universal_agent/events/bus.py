"""In-process async EventBus (§58). Swap-friendly: only this module changes
when moving to Redis Streams / NATS / Kafka."""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import DefaultDict, List, Optional

from .envelope import EventEnvelope
from .protocol import EventBusProtocol, EventHandler
from .types import EventType

log = logging.getLogger("ua.events.bus")


class InProcessEventBus(EventBusProtocol):
    """Async in-process event bus.

    Handlers are awaited sequentially per event type. A failing handler is
    caught, logged, and surfaced as EVENT_FAILED (system must not crash —
    §48 failure injection).
    """

    def __init__(self, emit_failure: Optional[EventHandler] = None) -> None:
        self._handlers: DefaultDict[EventType, List[EventHandler]] = defaultdict(list)
        self._closed = False
        self._emit_failure = emit_failure

    async def publish(self, event: EventEnvelope) -> None:
        if self._closed:
            raise RuntimeError("event bus is closed")
        for handler in list(self._handlers.get(event.event_type, [])):
            try:
                await handler(event)
            except Exception as exc:  # noqa: BLE001 — bus must survive
                log.exception("handler failed for %s", event.event_type.value)
                if self._emit_failure is not None:
                    try:
                        await self._emit_failure(event)
                    except Exception:  # noqa: BLE001
                        log.exception("failure handler also failed")

    def subscribe(self, event_type: EventType, handler: EventHandler) -> None:
        if handler not in self._handlers[event_type]:
            self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: EventType, handler: EventHandler) -> None:
        if handler in self._handlers[event_type]:
            self._handlers[event_type].remove(handler)

    async def close(self) -> None:
        self._closed = True
        self._handlers.clear()

    def __len__(self) -> int:
        return sum(len(v) for v in self._handlers.values())
