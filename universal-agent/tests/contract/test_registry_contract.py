"""Skill/Marketplace Registry contract tests (§22, §23, §43)."""
from __future__ import annotations

import pytest

from universal_agent.core.contracts import MarketplaceManifest, SkillManifest
from universal_agent.registry import CapabilityDenied, SkillRegistry


def _flight_skill() -> SkillManifest:
    return SkillManifest(
        skill_id="ctrip.flight",
        version="0.1.0",
        domains=["flight"],
        capabilities={"search": True, "detail": True, "availability": True,
                      "price_verify": True, "prepare_order": False,
                      "execute_order": False},
        transport=["browser"],
        risk={"execution": "none"},
    )


class TestSkillRegistry:
    def test_register_and_get(self):
        reg = SkillRegistry()
        reg.register_skill(_flight_skill())
        assert reg.get_skill("ctrip.flight") is not None
        assert reg.get_skill("nope") is None

    def test_list_by_domain(self):
        reg = SkillRegistry()
        reg.register_skill(_flight_skill())
        reg.register_skill(SkillManifest(skill_id="ctrip.hotel", domains=["hotel"],
                                         capabilities={"search": True}))
        flight_skills = reg.list_skills(domain="flight")
        assert [s.skill_id for s in flight_skills] == ["ctrip.flight"]

    def test_capability_granted(self):
        reg = SkillRegistry()
        reg.register_skill(_flight_skill())
        reg.assert_capability("ctrip.flight", "search")  # must not raise

    def test_capability_denied_when_not_granted(self):
        """§43: execute_order=false in manifest → registry rejects."""
        reg = SkillRegistry()
        reg.register_skill(_flight_skill())
        with pytest.raises(CapabilityDenied):
            reg.assert_capability("ctrip.flight", "execute_order")

    def test_capability_denied_unknown_skill(self):
        reg = SkillRegistry()
        with pytest.raises(CapabilityDenied):
            reg.assert_capability("ghost.skill", "search")


class TestMarketplaceRegistry:
    def test_register_and_health(self):
        reg = SkillRegistry()
        reg.register_marketplace(MarketplaceManifest(
            id="ctrip", domains=["flight", "hotel", "railway"],
            capabilities={"search": True, "detail": True, "price_verify": True},
            trust={"default_score": 0.9}, health="HEALTHY"))
        assert reg.get_marketplace("ctrip").trust["default_score"] == 0.9
        assert [m.id for m in reg.list_marketplaces(domain="flight", healthy_only=True)] == ["ctrip"]

    def test_source_health_drives_selection(self):
        """§53: degraded source excluded when healthy_only."""
        reg = SkillRegistry()
        reg.register_marketplace(MarketplaceManifest(id="a", domains=["flight"], health="HEALTHY"))
        reg.register_marketplace(MarketplaceManifest(id="b", domains=["flight"], health="DEGRADED"))
        reg.register_marketplace(MarketplaceManifest(id="c", domains=["flight"], health="UNAVAILABLE"))
        reg.register_marketplace(MarketplaceManifest(id="d", domains=["flight"], health="AUTH_REQUIRED"))
        assert [m.id for m in reg.list_marketplaces(domain="flight", healthy_only=True)] == ["a"]
