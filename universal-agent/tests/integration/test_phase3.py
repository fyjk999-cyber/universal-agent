"""PHASE 3 集成测试：Verification + 多轮历史累积 + Opportunity 统计。"""
from __future__ import annotations

from pathlib import Path

import pytest

from universal_agent.adapters.replay import make_fetchers
from universal_agent.coordinator.scanner import ShadowScanCoordinator
from universal_agent.core.contracts import TaskSpec
from universal_agent.events import EventType, InProcessEventBus
from universal_agent.memory import ObservationStore
from universal_agent.registry import MarketplaceManifest, SkillRegistry

FIXTURES = Path(__file__).resolve().parent.parent / "replay" / "fixtures"


def _registry() -> SkillRegistry:
    reg = SkillRegistry()
    for mid, trust in (("ctrip", 0.9), ("fliggy", 0.85)):
        reg.register_marketplace(MarketplaceManifest(
            id=mid, domains=["flight"], health="HEALTHY",
            trust={"default_score": trust}))
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
        notify_if={"historical_low": True, "opportunity_score_gte": 90},
    )


class TestPhase3VerificationInPipeline:
    @pytest.mark.asyncio
    async def test_verification_completed_event_emitted(self, tmp_path):
        bus = InProcessEventBus()
        seen = []

        async def collect(env):
            seen.append(env.event_type)

        bus.subscribe(EventType.VERIFICATION_COMPLETED, collect)
        coord = ShadowScanCoordinator(
            bus=bus, registry=_registry(),
            observations=ObservationStore(tmp_path / "obs"),
            fetchers=make_fetchers(FIXTURES, ["ctrip", "fliggy"]))
        out = await coord.scan(_task())
        await bus.close()
        assert EventType.VERIFICATION_COMPLETED in seen
        assert out.verification is not None
        assert out.verification.passed is True
        assert out.verification.evidence  # evidence attached

    @pytest.mark.asyncio
    async def test_multi_round_history_accumulates(self, tmp_path):
        obs = ObservationStore(tmp_path / "obs")
        coord = ShadowScanCoordinator(
            bus=InProcessEventBus(), registry=_registry(), observations=obs,
            fetchers=make_fetchers(FIXTURES, ["ctrip", "fliggy"]))
        await coord.scan(_task())
        await coord.scan(_task())  # round 2
        await coord.scan(_task())  # round 3
        total = len(obs.list_all())
        assert total == 15  # 5 listings × 3 rounds
        # observations are keyed by stable entity keys (not per-scan offer ids)
        keys = {o.target_key for o in obs.list_all()}
        assert keys
        for k in list(keys)[:1]:
            assert len(obs.price_history(k)) >= 1

    @pytest.mark.asyncio
    async def test_opportunity_uses_history_for_historical_low(self, tmp_path):
        obs = ObservationStore(tmp_path / "obs")
        coord = ShadowScanCoordinator(
            bus=InProcessEventBus(), registry=_registry(), observations=obs,
            fetchers=make_fetchers(FIXTURES, ["ctrip"]))
        await coord.scan(_task())
        out2 = await coord.scan(_task())
        assert out2.opportunity is not None
        # historical low should remain detectable with ≥1 history point
        assert isinstance(out2.opportunity.historical_low, bool)

    @pytest.mark.asyncio
    async def test_verification_confidence_feeds_opportunity(self, tmp_path):
        obs = ObservationStore(tmp_path / "obs")
        coord = ShadowScanCoordinator(
            bus=InProcessEventBus(), registry=_registry(), observations=obs,
            fetchers=make_fetchers(FIXTURES, ["ctrip", "fliggy"]))
        out = await coord.scan(_task())
        assert out.verification is not None
        assert out.opportunity is not None
        # verification confidence propagates into opportunity score components
        assert "verification" in out.opportunity.components
