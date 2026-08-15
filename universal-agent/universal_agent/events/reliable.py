"""Reliable Events（P2）— Outbox Dispatcher。

流程：
  pending → publish（调用 handler）→ delivered

失败处理：
  handler 抛异常 → attempts 递增；未达上限留在 PENDING（下次再试）
  达到 max_attempts → DEAD（DLQ：人工/补偿可查）

事件表（events）作为持久 EventStore；outbox 是投递队列。
Dispatcher 幂等：同一 outbox 行只投递一次（delivered 后不再处理）。
"""
from __future__ import annotations

import asyncio
import logging
from typing import Callable, Dict, Optional

from .envelope import EventEnvelope
from .types import EventType
from ..persistence.protocol import EventRepository, OutboxRepository

log = logging.getLogger("ua.events.reliable")

#: handler：event → 处理（可 async）
Handler = Callable[[EventEnvelope], None]


class OutboxDispatcher:
    def __init__(self, outbox: OutboxRepository,
                 events: Optional[EventRepository] = None,
                 handlers: Optional[Dict[EventType, Handler]] = None,
                 max_attempts: int = 3,
                 on_dead: Optional[Callable[[int, EventEnvelope, str], None]] = None) -> None:
        self.outbox = outbox
        self.events = events
        self.handlers = handlers or {}
        self.max_attempts = max_attempts
        self.on_dead = on_dead

    def register(self, event_type: EventType, handler: Handler) -> None:
        self.handlers[event_type] = handler

    async def dispatch_once(self, limit: int = 100) -> int:
        """投递一批 pending 事件。返回成功投递数。"""
        delivered = 0
        for row in self.outbox.pending(limit=limit):
            event = self._load(row)
            if event is None:
                self.outbox.mark_dead(row["outbox_id"], "malformed event data")
                continue
            handler = self.handlers.get(event.event_type)
            if handler is None:
                # 无 handler：视为已消费（持久存储仍在 events 表，可查）
                self.outbox.mark_delivered(row["outbox_id"])
                continue
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as exc:  # noqa: BLE001
                attempts = int(row.get("attempts") or 0) + 1
                if attempts >= self.max_attempts:
                    self.outbox.mark_dead(row["outbox_id"], str(exc))
                    log.error("event %s 达到最大重试，进入 DLQ: %s", event.event_id, exc)
                    if self.on_dead is not None:
                        self.on_dead(row["outbox_id"], event, str(exc))
                else:
                    self._bump_attempts(row["outbox_id"], attempts)
                    log.warning("event %s handler 失败（attempt %s/%s）: %s",
                                event.event_id, attempts, self.max_attempts, exc)
                continue
            # 成功 → 持久化事件 + 标记 delivered
            if self.events is not None:
                self.events.append(event)
            self.outbox.mark_delivered(row["outbox_id"])
            delivered += 1
        return delivered

    async def run_forever(self, interval_seconds: float = 1.0) -> None:
        """持续投递循环（供 daemon/service 后台运行）。"""
        while True:
            try:
                await self.dispatch_once()
            except Exception as exc:  # noqa: BLE001
                log.exception("dispatch cycle failed: %s", exc)
            await asyncio.sleep(interval_seconds)

    # ---- helpers ----
    def _load(self, row) -> Optional[EventEnvelope]:
        import json
        try:
            return EventEnvelope.model_validate(json.loads(row["data"]))
        except Exception:  # noqa: BLE001
            return None

    def _bump_attempts(self, outbox_id: int, attempts: int) -> None:
        self.outbox.bump_attempts(outbox_id, attempts)
