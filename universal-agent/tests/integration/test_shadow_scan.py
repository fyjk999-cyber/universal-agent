"""End-to-end Shadow Scan test (§61, §69, §72) — full event-driven pipeline.

Proves: TaskSpec → QueryPlan → SourcePlan → Replay fixtures → RawListing →
Normalize → Candidate/Offer/Quote → Score → Top5 → Opportunity → Notify,
all SHADOW MODE (no purchase, no network).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from universal_agent.adapters.replay import make_fetchers
from universal_agent.coordinator.scanner import ShadowScanCoordinator
from universal_agent.core.contracts import TaskSpec
from universal_agent.events import EventBusProtocol, EventEnvelope, EventType, InProcessEventBus
from universal_agent.memory import ObservationStore
from universal_agent.registry import MarketplaceManifest, SkillRegistry

FIXTURES = Path(__file__).resolve().parent.parent / "replay" / "fixtures"


def _registry() -> SkillRegistry:
    reg = SkillRegistry()
    for mid in ("ctrip", "fliggy"):
        reg.register_marketplace(MarketplaceManifest(
            id=mid, domains=["flight"], health="HEALTHY",
            capabilities={"search": True}, trust={"default_score": 0.9 if mid == "ctrip" else 0.85}))
    return reg


def _task() -> TaskSpec:
    return TaskSpec(
        id="queenstown-travel-watch", type="watch", domain="flight",
        search_space={
            "origin": ["HGH", "PVG", "SHA"],
            "destination": ["ZQN"],
            "departure": {"start": "2026-08-30", "end": "2026-09-03"},
            "nights": {"min": 6, "preferred": 7, "max": 8},
        },
        notify_if={"opportunity_score_gte": 90, "historical_low": True,
                   "price_drop_cny_gte": 300},
    )


class TestShadowScan:
    @pytest.mark.asyncio
    async def test_full_pipeline_emits_event_chain(self, tmp_path):
        bus = InProcessEventBus()
        seen: list[EventEnvelope] = []

        async def collect(env: EventEnvelope):
            seen.append(env)

        for t in EventType:
            bus.subscribe(t, collect)

        reg = _registry()
        coord = ShadowScanCoordinator(
            bus=bus,
            registry=reg,
            observations=ObservationStore(tmp_path / "obs"),
            fetchers=make_fetchers(FIXTURES, ["ctrip", "fliggy"]),
        )

        outcome = await coord.scan(_task())
        await bus.close()

        assert outcome.raw_listings
        assert outcome.candidates
        assert outcome.quotes
        assert len(outcome.top5) == 5
        assert outcome.opportunity is not None

        # whole event chain must have fired (§7, §51)
        types = {e.event_type for e in seen}
        for expected in (EventType.SCAN_REQUESTED, EventType.RAW_LISTING_DISCOVERED,
                         EventType.CANDIDATE_CREATED, EventType.OFFER_DISCOVERED,
                         EventType.QUOTE_OBSERVED, EventType.SCORE_UPDATED,
                         EventType.MATERIAL_CHANGE_DETECTED, EventType.OPPORTUNITY_DETECTED,
                         EventType.NOTIFICATION_REQUESTED, EventType.NOTIFICATION_SENT,
                         EventType.SCAN_COMPLETED):
            assert expected in types, f"missing event {expected.value}"

        # all events share one trace_id (§51)
        traces = {e.trace_id for e in seen}
        assert len(traces) == 1

        # top5 are distinct listings
        assert len({r.listing_id for r in outcome.top5}) == 5

    @pytest.mark.asyncio
    async def test_cross_source_merge_reduces_candidates(self, tmp_path):
        """ctrip + fliggy see the same PVG→ZQN itinerary → merged (§21, §62)."""
        bus = InProcessEventBus()
        reg = _registry()
        coord = ShadowScanCoordinator(
            bus=bus, registry=reg,
            observations=ObservationStore(tmp_path / "obs"),
            fetchers=make_fetchers(FIXTURES, ["ctrip", "fliggy"]),
        )
        outcome = await coord.scan(_task())
        await bus.close()

        keys = {c.entity_key for c in outcome.candidates}
        # 5 raw listings from 2 sources; PVG 08-30 appears in both → merged
        assert len(keys) < len(outcome.raw_listings)
        assert len(outcome.candidates) == len(keys)

    @pytest.mark.asyncio
    async def test_observations_persisted(self, tmp_path):
        bus = InProcessEventBus()
        reg = _registry()
        obs = ObservationStore(tmp_path / "obs")
        coord = ShadowScanCoordinator(
            bus=bus, registry=reg, observations=obs,
            fetchers=make_fetchers(FIXTURES, ["ctrip"]),
        )
        await coord.scan(_task())
        await bus.close()
        assert obs.list_all()  # price facts recorded
        assert all(o.kind == "price" for o in obs.list_all())

    @pytest.mark.asyncio
    async def test_shadow_mode_no_execution(self, tmp_path):
        """§61/§56: shadow scan must never execute purchase actions."""
        bus = InProcessEventBus()
        executed = []

        from universal_agent.actions import ActionGateway
        gw = ActionGateway()

        async def guard(env: EventEnvelope):
            if env.event_type in (EventType.ACTION_EXECUTION_REQUESTED,
                                  EventType.ACTION_EXECUTED):
                executed.append(env)

        bus.subscribe(EventType.ACTION_EXECUTION_REQUESTED, guard)
        bus.subscribe(EventType.ACTION_EXECUTED, guard)

        reg = _registry()
        coord = ShadowScanCoordinator(
            bus=bus, registry=reg,
            observations=ObservationStore(tmp_path / "obs"),
            fetchers=make_fetchers(FIXTURES, ["ctrip"]),
        )
        await coord.scan(_task())
        await bus.close()
        assert executed == []  # no action events in shadow mode
