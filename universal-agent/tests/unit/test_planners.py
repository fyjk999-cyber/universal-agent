"""Query Planner + Source Planner tests (§24, §25)."""
from __future__ import annotations

from universal_agent.coordinator.query_planner import build_query_plan
from universal_agent.coordinator.source_planner import plan_sources
from universal_agent.core.contracts import MarketplaceManifest, TaskSpec
from universal_agent.registry import SkillRegistry


def _task() -> TaskSpec:
    return TaskSpec(
        id="t1", type="watch", domain="flight",
        search_space={
            "origin": ["HGH", "PVG", "SHA"],
            "destination": ["ZQN"],
            "departure": {"start": "2026-08-30", "end": "2026-09-03"},
            "nights": {"min": 6, "preferred": 7, "max": 8},
        },
    )


class TestQueryPlanner:
    def test_query_count_bounded(self):
        plan = build_query_plan(_task(), max_queries=60)
        assert 0 < len(plan.queries) <= 60

    def test_preferred_nights_first(self):
        plan = build_query_plan(_task(), max_queries=60)
        first = plan.queries[0]
        assert first.nights == 7  # preferred first

    def test_covers_all_origins(self):
        plan = build_query_plan(_task(), max_queries=200)
        origins = {q.origin for q in plan.queries}
        assert origins == {"HGH", "PVG", "SHA"}

    def test_destination_fixed(self):
        plan = build_query_plan(_task())
        assert {q.destination for q in plan.queries} == {"ZQN"}


class TestSourcePlanner:
    def test_healthy_sources_only(self):
        reg = SkillRegistry()
        reg.register_marketplace(MarketplaceManifest(id="a", domains=["flight"], health="HEALTHY"))
        reg.register_marketplace(MarketplaceManifest(id="b", domains=["flight"], health="DEGRADED"))
        plan = plan_sources("t1", "flight", reg)
        assert [m.id for m in plan.sources] == ["a"]

    def test_trust_order(self):
        reg = SkillRegistry()
        reg.register_marketplace(MarketplaceManifest(id="low", domains=["flight"],
                                                     health="HEALTHY",
                                                     trust={"default_score": 0.5}))
        reg.register_marketplace(MarketplaceManifest(id="high", domains=["flight"],
                                                     health="HEALTHY",
                                                     trust={"default_score": 0.95}))
        plan = plan_sources("t1", "flight", reg)
        assert [m.id for m in plan.sources] == ["high", "low"]
