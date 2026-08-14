"""PHASE 3b 集成测试：真实源接入管线 + Source Health 降级（§48/§53）。

真实 Skyscanner 抓取不在此测试（需要浏览器+网络，慢）。用可控的假 fetcher
验证：1) 源失败 → DEGRADED → 后续跳过；2) skyscanner manifest 正确注册。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from universal_agent.adapters.skyscanner import (
    skyscanner_marketplace_manifest,
    skyscanner_skill_manifest,
)
from universal_agent.coordinator.scanner import ShadowScanCoordinator
from universal_agent.core.contracts import RawListing, TaskSpec
from universal_agent.events import InProcessEventBus
from universal_agent.memory import ObservationStore
from universal_agent.registry import MarketplaceManifest, SkillRegistry

FIXTURES = Path(__file__).resolve().parent.parent / "replay" / "fixtures"


def _task() -> TaskSpec:
    return TaskSpec(
        id="t-live", type="watch", domain="flight",
        search_space={
            "origin": ["PVG"], "destination": ["ZQN"],
            "departure": {"start": "2026-08-31", "end": "2026-08-31"},
            "nights": {"min": 7, "preferred": 7, "max": 7},
        },
    )


def _registry() -> SkillRegistry:
    reg = SkillRegistry()
    reg.register_marketplace(MarketplaceManifest(
        id="replay-ctrip", domains=["flight"], health="HEALTHY",
        trust={"default_score": 0.9}))
    reg.register_marketplace(skyscanner_marketplace_manifest())
    return reg


class TestRealSourceManifests:
    def test_skyscanner_skill_declares_capabilities(self):
        skill = skyscanner_skill_manifest()
        assert skill.skill_id == "skyscanner.flight"
        assert skill.capabilities["search"] is True
        assert skill.capabilities["execute_order"] is False  # §23/§56

    def test_skyscanner_marketplace_health(self):
        m = skyscanner_marketplace_manifest()
        assert m.id == "skyscanner"
        assert m.health == "HEALTHY"
        assert m.trust["default_score"] > 0.5


class TestSourceHealthDegradation:
    @pytest.mark.asyncio
    async def test_failing_source_degrades_and_continues(self, tmp_path):
        """§48/§53: 一个源失败不中断整体；失败源标记 DEGRADED。"""
        reg = _registry()

        def good_fetcher(query):
            return [RawListing.model_validate({
                "listing_id": f"ok-{query.origin}", "source": "replay-ctrip",
                "marketplace_id": "replay-ctrip", "task_id": "t-live",
                "origin_airport": query.origin, "dest_airport": "ZQN",
                "depart_date": query.depart_date, "return_date": query.return_date,
                "nights": 7, "price_cny": 5000.0,
                "outbound": {"segments": [], "total_min": 600, "stops": 0},
                "inbound": {"segments": [], "total_min": 480, "stops": 0},
            })]

        def bad_fetcher(query):
            raise RuntimeError("skyscanner down")

        coord = ShadowScanCoordinator(
            bus=InProcessEventBus(), registry=reg,
            observations=ObservationStore(tmp_path / "obs"),
            fetchers={"replay-ctrip": good_fetcher, "skyscanner": bad_fetcher},
            max_queries=5)
        out = await coord.scan(_task())
        # 好源数据仍在；坏源被降级
        assert out.raw_listings
        assert reg.get_marketplace("skyscanner").health == "DEGRADED"
        assert reg.get_marketplace("replay-ctrip").health == "HEALTHY"

    @pytest.mark.asyncio
    async def test_degraded_source_excluded_next_plan(self):
        """§53: DEGRADED 源在 healthy_only 选源中被排除。"""
        reg = _registry()
        reg.set_marketplace_health("skyscanner", "DEGRADED")
        from universal_agent.coordinator.source_planner import plan_sources
        plan = plan_sources("t-live", "flight", reg)  # healthy_only 默认
        ids = [m.id for m in plan.sources]
        assert "skyscanner" not in ids
        assert "replay-ctrip" in ids
