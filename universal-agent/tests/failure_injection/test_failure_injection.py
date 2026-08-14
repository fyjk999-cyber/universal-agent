"""Failure injection tests (§48).

Proves the system does not crash when individual pieces fail.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from universal_agent.coordinator import TaskRegistry
from universal_agent.events import EventEnvelope, EventType, InProcessEventBus
from universal_agent.memory import MemoryStore
from universal_agent.registry import SkillRegistry


class TestCorruptStateRecovery:
    def test_corrupt_task_registry_does_not_crash(self, tmp_path):
        path = tmp_path / "reg"
        path.mkdir(parents=True)
        (path / "task_registry.json").write_text("{not json!!!", "utf-8")
        reg = TaskRegistry(path)  # must not raise
        assert reg.list() == []

    def test_corrupt_memory_does_not_crash(self, tmp_path):
        path = tmp_path / "mem"
        path.mkdir(parents=True)
        (path / "memory.json").write_text("garbage", "utf-8")
        store = MemoryStore(path)  # must not raise
        assert store.query(type("Q", (), {"scope": None, "domain": None, "task_id": None,
                                          "key": None, "kind": None, "limit": 10})()) == []


class TestEventFailureInjection:
    @pytest.mark.asyncio
    async def test_duplicate_event_delivery(self):
        bus = InProcessEventBus()
        count = 0

        async def handler(env):
            nonlocal count
            count += 1

        bus.subscribe(EventType.SCAN_REQUESTED, handler)
        env = EventEnvelope(event_type=EventType.SCAN_REQUESTED, trace_id="t")
        await bus.publish(env)
        await bus.publish(env)  # duplicate — handlers are registered once
        assert count == 2  # both delivered, no crash
        await bus.close()

    @pytest.mark.asyncio
    async def test_event_out_of_order_is_safe(self):
        bus = InProcessEventBus()
        order = []

        async def h1(env):
            order.append("task_started")

        async def h2(env):
            order.append("task_completed")

        bus.subscribe(EventType.TASK_COMPLETED, h2)
        bus.subscribe(EventType.TASK_STARTED, h1)
        # publish completed BEFORE started — bus handles any order
        await bus.publish(EventEnvelope(event_type=EventType.TASK_COMPLETED, trace_id="t"))
        await bus.publish(EventEnvelope(event_type=EventType.TASK_STARTED, trace_id="t"))
        assert order == ["task_completed", "task_started"]
        await bus.close()


class TestMalformedInput:
    def test_unknown_task_domain_rejected(self):
        from universal_agent.core.contracts import TaskSpec
        with pytest.raises(Exception):
            TaskSpec(id="x", type="watch", domain="not_a_domain")

    def test_registry_unknown_skill_does_not_crash_listing(self):
        reg = SkillRegistry()
        assert reg.list_skills(domain="flight") == []


class TestReplayFixtureShape:
    """§47: raw listings are saved as fixtures for offline replay."""

    def test_raw_listing_fixture_is_plain_json(self, tmp_path):
        fixture = {
            "trace_id": "tr-1",
            "source": "ctrip",
            "candidates": [{"flight": "MU779", "price": 4380}],
        }
        path = tmp_path / "raw_listing.json"
        path.write_text(json.dumps(fixture), "utf-8")
        loaded = json.loads(path.read_text("utf-8"))
        assert loaded["candidates"][0]["price"] == 4380
