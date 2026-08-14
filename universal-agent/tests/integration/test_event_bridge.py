"""Event bridge integration tests (hosts → bus)."""
from __future__ import annotations

import asyncio

import pytest

from universal_agent.events import EventEnvelope, EventType, InProcessEventBus
from universal_agent.hosts.deepseek_harness import HarnessEventBridge
from universal_agent.hosts.jarvis import JarvisEventBridge


class TestHarnessEventBridge:
    @pytest.mark.asyncio
    async def test_publish_wraps_envelope(self):
        bus = InProcessEventBus()
        seen = []

        async def handler(env: EventEnvelope):
            seen.append(env)

        bus.subscribe(EventType.SCAN_REQUESTED, handler)
        bridge = HarnessEventBridge(bus)
        env = await bridge.publish(EventType.SCAN_REQUESTED, {"origin": "PVG"},
                                   task_id="t1")
        await asyncio.sleep(0.01)
        assert env.event_type == EventType.SCAN_REQUESTED
        assert env.task_id == "t1"
        assert env.source == "deepseek_harness"
        assert len(seen) == 1
        await bus.close()


class TestJarvisEventBridge:
    @pytest.mark.asyncio
    async def test_publish_marks_jarvis_source(self):
        bus = InProcessEventBus()
        bridge = JarvisEventBridge(bus)
        env = await bridge.publish(EventType.NOTIFICATION_SENT, {"ok": True})
        assert env.source == "jarvis"
        await bus.close()
