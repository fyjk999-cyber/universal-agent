"""P0.9-4 回归测试：Final Ranking Eligibility Gate。

规则：
- PARTIAL 绝不进入 Final Top5
- PARTIAL 可进入 preliminary pool
- PARTIAL 不触发购买建议/通知
- PARTIAL 不创建 ActionPlan
- STRUCTURED 可进 Final Top5
- VERIFIED 可 ACTION_ELIGIBLE
- 最便宜 PARTIAL 也不能击败 STRUCTURED 候选
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from universal_agent.core.contracts import (
    DataCompleteness,
    RankEligibility,
    RawLeg,
    RawListing,
    TaskSpec,
    rank_eligibility,
)
from universal_agent.adapters.replay import make_fetchers
from universal_agent.coordinator.scanner import ShadowScanCoordinator
from universal_agent.events import InProcessEventBus
from universal_agent.memory import ObservationStore
from universal_agent.registry import MarketplaceManifest, SkillRegistry

FIXTURES = Path(__file__).resolve().parent.parent / "replay" / "fixtures"


def _seg() -> dict:
    return {"airline": "NZ", "flight_no": "NZ288", "dep_airport": "PVG",
            "arr_airport": "AKL", "dep_time": "14:30", "arr_time": "06:30",
            "dep_date": "2026-08-31", "arr_date": "2026-09-01", "duration_min": 660}


def _listing(lid: str, price: float, completeness: str,
             with_segments: bool = False) -> RawListing:
    if with_segments:
        out = RawLeg(segments=[_seg()], total_min=810, stops=1, layovers=[120])
        inn = RawLeg(segments=[_seg()], total_min=870, stops=1, layovers=[120])
    else:
        out = RawLeg(segments=[], total_min=0, stops=-1)
        inn = RawLeg(segments=[], total_min=0, stops=-1)
    return RawListing(
        listing_id=lid, source="s", marketplace_id="s", task_id="t1",
        origin_airport="PVG", dest_airport="ZQN",
        depart_date="2026-08-31", return_date="2026-09-07", nights=7,
        price_cny=price,
        outbound=out, inbound=inn, luggage={},
        extra={"completeness": completeness},
    )


def _task() -> TaskSpec:
    return TaskSpec(
        id="t-gate", type="watch", domain="flight",
        search_space={"origin": ["PVG"], "destination": ["ZQN"],
                      "departure": {"start": "2026-08-31", "end": "2026-08-31"},
                      "nights": {"min": 7, "preferred": 7, "max": 7}},
        notify_if={"historical_low": True, "opportunity_score_gte": 80},
    )


class TestRankEligibility:
    def test_partial_to_preliminary(self):
        l = _listing("p", 2500, DataCompleteness.PARTIAL.value)
        assert rank_eligibility(l) == RankEligibility.PRELIMINARY

    def test_structured_to_final(self):
        l = _listing("s", 4380, DataCompleteness.STRUCTURED.value, with_segments=True)
        assert rank_eligibility(l) == RankEligibility.FINAL_ELIGIBLE

    def test_verified_to_action(self):
        l = _listing("v", 4380, DataCompleteness.VERIFIED.value, with_segments=True)
        assert rank_eligibility(l) == RankEligibility.ACTION_ELIGIBLE


class TestGateInPipeline:
    @pytest.mark.asyncio
    async def test_partial_never_enters_final_top5(self, tmp_path):
        """只有 PARTIAL → Final Top5 为空；preliminary 有值。"""
        reg = SkillRegistry()
        reg.register_marketplace(MarketplaceManifest(id="s", domains=["flight"],
                                                     health="HEALTHY"))
        partial = _listing("p1", 2500, DataCompleteness.PARTIAL.value)
        partial2 = _listing("p2", 2800, DataCompleteness.PARTIAL.value)

        def fetcher(query):
            return [partial, partial2]

        coord = ShadowScanCoordinator(
            bus=InProcessEventBus(), registry=reg,
            observations=ObservationStore(tmp_path / "obs"),
            fetchers={"s": fetcher})
        out = await coord.scan(_task())
        assert out.top5 == []  # PARTIAL 不进 Final Top5
        assert len(out.preliminary_top) == 2  # 但可进初选池

    @pytest.mark.asyncio
    async def test_cheapest_partial_cannot_beat_structured(self, tmp_path):
        """最便宜 PARTIAL（¥2500）也不能击败 STRUCTURED（¥4380）候选。"""
        reg = SkillRegistry()
        reg.register_marketplace(MarketplaceManifest(id="s", domains=["flight"],
                                                     health="HEALTHY"))
        partial = _listing("cheap-partial", 2500, DataCompleteness.PARTIAL.value)
        structured = _listing("structured", 4380, DataCompleteness.STRUCTURED.value,
                              with_segments=True)

        def fetcher(query):
            return [partial, structured]

        coord = ShadowScanCoordinator(
            bus=InProcessEventBus(), registry=reg,
            observations=ObservationStore(tmp_path / "obs"),
            fetchers={"s": fetcher})
        out = await coord.scan(_task())
        # Final Top5 只含 STRUCTURED；便宜的 PARTIAL 只在 preliminary
        assert [r.listing_id for r in out.top5] == ["structured"]
        assert any(r.listing_id == "cheap-partial" for r in out.preliminary_top)

    @pytest.mark.asyncio
    async def test_partial_never_triggers_notification(self, tmp_path):
        """PARTIAL-only → 不触发通知（不产生购买建议）。"""
        reg = SkillRegistry()
        reg.register_marketplace(MarketplaceManifest(id="s", domains=["flight"],
                                                     health="HEALTHY"))
        partial = _listing("p1", 2500, DataCompleteness.PARTIAL.value)

        def fetcher(query):
            return [partial]

        coord = ShadowScanCoordinator(
            bus=InProcessEventBus(), registry=reg,
            observations=ObservationStore(tmp_path / "obs"),
            fetchers={"s": fetcher})
        out = await coord.scan(_task())
        assert out.notified is False  # PARTIAL 不触发购买建议
        assert out.opportunity is None

    def test_partial_never_creates_action_plan(self):
        """PARTIAL 候选不生成 ActionPlan（domain 层 gate）。"""
        partial = _listing("p", 2500, DataCompleteness.PARTIAL.value)
        assert rank_eligibility(partial) == RankEligibility.PRELIMINARY
        # ACTION_ELIGIBLE 才允许 prepare
        verified = _listing("v", 4380, DataCompleteness.VERIFIED.value, with_segments=True)
        assert rank_eligibility(verified) == RankEligibility.ACTION_ELIGIBLE

    @pytest.mark.asyncio
    async def test_structured_can_enter_final_top5(self, tmp_path):
        reg = SkillRegistry()
        reg.register_marketplace(MarketplaceManifest(id="s", domains=["flight"],
                                                     health="HEALTHY"))
        structured = _listing("s1", 4380, DataCompleteness.STRUCTURED.value, with_segments=True)

        def fetcher(query):
            return [structured]

        coord = ShadowScanCoordinator(
            bus=InProcessEventBus(), registry=reg,
            observations=ObservationStore(tmp_path / "obs"),
            fetchers={"s": fetcher})
        out = await coord.scan(_task())
        assert [r.listing_id for r in out.top5] == ["s1"]
