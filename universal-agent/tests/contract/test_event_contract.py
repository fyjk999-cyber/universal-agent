"""Event Contract tests (§5, §6, §45)."""
from __future__ import annotations

import json

import pytest

from universal_agent.events import EventBusProtocol, EventEnvelope, EventType, InProcessEventBus
from universal_agent.events.envelope import EventEnvelope


class TestEventEnvelope:
    def test_required_fields(self):
        env = EventEnvelope(event_type=EventType.SCAN_REQUESTED, trace_id="tr-1",
                            task_id="t1", payload={"origin": "PVG"})
        assert env.event_id
        assert env.schema_version == "1.0"
        assert env.created_at is not None

    def test_all_required_keys_present(self):
        env = EventEnvelope(event_type=EventType.SCAN_REQUESTED, trace_id="tr-1")
        data = env.model_dump(mode="json")
        for key in ("event_id", "event_type", "schema_version", "trace_id",
                    "task_id", "source", "created_at", "payload"):
            assert key in data, f"missing {key}"

    def test_full_event_type_set(self):
        expected = {
            "TASK_CREATED", "TASK_UPDATED", "TASK_STARTED", "TASK_COMPLETED",
            "TASK_FAILED", "WATCH_STARTED", "WATCH_PAUSED", "WATCH_RESUMED",
            "WATCH_EXPIRED", "SCAN_REQUESTED", "SCAN_COMPLETED",
            "RAW_LISTING_DISCOVERED", "CANDIDATE_CREATED", "CANDIDATE_UPDATED",
            "OFFER_DISCOVERED", "QUOTE_OBSERVED", "VERIFICATION_REQUESTED",
            "VERIFICATION_COMPLETED", "SCORE_UPDATED", "MATERIAL_CHANGE_DETECTED",
            "OPPORTUNITY_DETECTED", "NOTIFICATION_REQUESTED", "NOTIFICATION_SENT",
            "ACTION_PLAN_CREATED", "APPROVAL_REQUESTED", "ACTION_APPROVED",
            "ACTION_REJECTED", "ACTION_EXECUTION_REQUESTED", "ACTION_EXECUTED",
            "ACTION_FAILED", "MEMORY_UPDATE_REQUESTED", "MEMORY_UPDATED",
        }
        actual = {e.value for e in EventType}
        assert expected <= actual, f"missing events: {expected - actual}"


class TestEventBus:
    @pytest.mark.asyncio
    async def test_publish_subscribe(self):
        bus = InProcessEventBus()
        seen = []

        async def handler(env: EventEnvelope):
            seen.append(env)

        bus.subscribe(EventType.SCAN_REQUESTED, handler)
        env = EventEnvelope(event_type=EventType.SCAN_REQUESTED, trace_id="tr-2")
        await bus.publish(env)
        assert seen == [env]
        await bus.close()

    @pytest.mark.asyncio
    async def test_handler_failure_does_not_crash_bus(self):
        """§48 failure injection: a throwing handler must not crash the bus."""
        bus = InProcessEventBus()

        async def bad_handler(env):
            raise RuntimeError("boom")

        async def good_handler(env):
            pass

        bus.subscribe(EventType.TASK_STARTED, bad_handler)
        bus.subscribe(EventType.TASK_STARTED, good_handler)
        env = EventEnvelope(event_type=EventType.TASK_STARTED, trace_id="tr-3")
        await bus.publish(env)  # must not raise
        await bus.close()

    def test_bus_implements_protocol(self):
        assert issubclass(InProcessEventBus, EventBusProtocol)

    @pytest.mark.asyncio
    async def test_publish_after_close_raises(self):
        bus = InProcessEventBus()
        await bus.close()
        with pytest.raises(RuntimeError):
            await bus.publish(EventEnvelope(event_type=EventType.SCAN_REQUESTED,
                                            trace_id="tr-4"))


class TestEventBridgeShape:
    def test_envelope_is_plain_json(self):
        env = EventEnvelope(event_type=EventType.QUOTE_OBSERVED, trace_id="tr-5",
                            payload={"price": 4380})
        dumped = env.model_dump(mode="json")
        json.dumps(dumped)  # must serialize without error
        assert dumped["payload"] == {"price": 4380}
