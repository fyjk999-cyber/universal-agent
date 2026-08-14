"""P0.9-8 集成测试 2：Flight Pipeline — Eligibility Gate 全流程。"""
from __future__ import annotations

from pathlib import Path

import pytest

from universal_agent.core.contracts import (
    DataCompleteness,
    RawLeg,
    RawListing,
    TaskSpec,
)
from universal_agent.coordinator.scanner import ShadowScanCoordinator
from universal_agent.events import EventType, InProcessEventBus
from universal_agent.memory import ObservationStore
from universal_agent.registry import MarketplaceManifest, SkillRegistry


def _seg() -> dict:
    return {"airline": "NZ", "flight_no": "NZ288", "dep_airport": "PVG",
            "arr_airport": "AKL", "dep_time": "14:30", "arr_time": "06:30",
            "dep_date": "2026-08-31", "arr_date": "2026-09-01", "duration_min": 660}


def _partial(lid: str, price: float) -> RawListing:
    return RawListing(
        listing_id=lid, source="skyscanner", marketplace_id="skyscanner",
        task_id="t1", origin_airport="PVG", dest_airport="ZQN",
        depart_date="2026-08-31", return_date="2026-09-07", nights=7,
        price_cny=price,
        outbound=RawLeg(segments=[], total_min=935, stops=-1),
        inbound=RawLeg(segments=[], total_min=0, stops=-1),
        luggage={}, extra={"completeness": DataCompleteness.PARTIAL.value})


def _structured(lid: str, price: float) -> RawListing:
    return RawListing(
        listing_id=lid, source="ctrip", marketplace_id="ctrip", task_id="t1",
        origin_airport="PVG", dest_airport="ZQN",
        depart_date="2026-08-31", return_date="2026-09-07", nights=7,
        price_cny=price,
        outbound=RawLeg(segments=[_seg()], total_min=810, stops=1, layovers=[120]),
        inbound=RawLeg(segments=[_seg()], total_min=870, stops=1, layovers=[120]),
        luggage={}, extra={"completeness": DataCompleteness.STRUCTURED.value})


def _task() -> TaskSpec:
    return TaskSpec(
        id="t1", type="watch", domain="flight",
        search_space={"origin": ["PVG"], "destination": ["ZQN"],
                      "departure": {"start": "2026-08-31", "end": "2026-08-31"},
                      "nights": {"min": 7, "preferred": 7, "max": 7}},
        notify_if={"historical_low": True, "opportunity_score_gte": 80},
    )


def _reg() -> SkillRegistry:
    reg = SkillRegistry()
    reg.register_marketplace(MarketplaceManifest(id="skyscanner", domains=["flight"],
                                                 health="HEALTHY"))
    reg.register_marketplace(MarketplaceManifest(id="ctrip", domains=["flight"],
                                                 health="HEALTHY"))
    return reg


class TestFlightPipelineGate:
    @pytest.mark.asyncio
    async def test_partial_then_structured_flow(self, tmp_path):
        """PARTIAL → 不进 Final Top5 → 补 detail → STRUCTURED → Final + 通知。"""
        # 阶段 1：只有 PARTIAL（Skyscanner search）
        partial = _partial("sky-1", 2500)
        events = []

        async def collect(env):
            events.append(env.event_type)

        bus = InProcessEventBus()
        bus.subscribe(EventType.SCAN_COMPLETED, collect)
        reg = _reg()

        def fetcher1(query):
            return [partial]

        coord1 = ShadowScanCoordinator(bus=bus, registry=reg,
                                       observations=ObservationStore(tmp_path / "obs"),
                                       fetchers={"skyscanner": fetcher1})
        out1 = await coord1.scan(_task())
        assert out1.top5 == []  # PARTIAL 不进 Final Top5
        assert len(out1.preliminary_top) == 1  # 疑似低价待验证
        assert out1.notified is False  # 不触发购买建议

        # 阶段 2：补 detail（ctrip STRUCTURED）→ 进 Final + 通知
        structured = _structured("ctrip-1", 4380)

        def fetcher2(query):
            return [partial, structured]

        coord2 = ShadowScanCoordinator(bus=bus, registry=reg,
                                       observations=ObservationStore(tmp_path / "obs"),
                                       fetchers={"skyscanner": fetcher2})
        out2 = await coord2.scan(_task())
        assert [r.listing_id for r in out2.top5] == ["ctrip-1"]  # 只有 STRUCTURED 进 Final
        assert any(r.listing_id == "sky-1" for r in out2.preliminary_top)
        await bus.close()

    @pytest.mark.asyncio
    async def test_verification_and_trigger_only_for_final(self, tmp_path):
        """只有 STRUCTURED 时才有 verification + 通知触发。"""
        bus = InProcessEventBus()
        seen = []

        async def collect(env):
            seen.append(env.event_type)

        bus.subscribe(EventType.OPPORTUNITY_DETECTED, collect)
        bus.subscribe(EventType.VERIFICATION_COMPLETED, collect)
        reg = _reg()
        structured = _structured("ctrip-1", 4380)
        partial = _partial("sky-1", 2500)

        def fetcher(query):
            return [partial, structured]

        coord = ShadowScanCoordinator(bus=bus, registry=reg,
                                      observations=ObservationStore(tmp_path / "obs"),
                                      fetchers={"skyscanner": fetcher})
        out = await coord.scan(_task())
        assert EventType.OPPORTUNITY_DETECTED in seen
        assert EventType.VERIFICATION_COMPLETED in seen
        assert out.verification is not None
        await bus.close()
