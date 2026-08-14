"""EventBusProtocol — business code depends only on this (§4, §58)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Awaitable, Callable, Optional

from .envelope import EventEnvelope
from .types import EventType

#: handler receives an EventEnvelope; may be async
EventHandler = Callable[[EventEnvelope], Awaitable[None]]


class EventBusProtocol(ABC):
    """In-process first version; later Redis Streams / NATS / Kafka must
    implement the same protocol so business code never changes."""

    @abstractmethod
    async def publish(self, event: EventEnvelope) -> None:
        """Publish an event to all subscribed handlers of its type."""

    @abstractmethod
    def subscribe(self, event_type: EventType, handler: EventHandler) -> None:
        """Register a handler for one event type."""

    @abstractmethod
    def unsubscribe(self, event_type: EventType, handler: EventHandler) -> None:
        """Remove a handler."""

    @abstractmethod
    async def close(self) -> None:
        """Shut down the bus, draining in-flight handlers."""
