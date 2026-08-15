"""P5 — Skill Runtime：SkillProtocol + CapabilityResolver。

验收：
1. SkillProtocol 接口：search/detail/verify/availability/prepare_action/health_check
2. CapabilityResolver：按 domain/capability/health/cost/trust 选最佳 skill
3. 高危 execute_action 只能经 ActionGateway（Skill 不直接执行）
4. 无满足条件 skill → 明确失败（fail-closed）
"""
from __future__ import annotations

from pathlib import Path

import pytest

from universal_agent.core.contracts import MarketplaceManifest, SkillManifest


def test_skill_protocol_interface() -> None:
    """SkillProtocol 定义 6 个核心方法。"""
    from universal_agent.registry.skills.protocol import SkillProtocol
    for m in ("search", "detail", "verify", "availability",
              "prepare_action", "health_check"):
        assert hasattr(SkillProtocol, m), f"missing method: {m}"


def test_resolver_picks_healthy_trusted(tmp_path: Path) -> None:
    """Resolver 在候选里选 health=HEALTHY + trust 最高者。"""
    from universal_agent.registry.skills.resolver import CapabilityResolver
    from universal_agent.registry.registry import SkillRegistry

    reg = SkillRegistry()
    reg.register_skill(SkillManifest(
        skill_id="ctrip-flight", domains=["flight"],
        capabilities={"search": True, "detail": True},
        health="HEALTHY", cost=0.5, trust=0.9))
    reg.register_skill(SkillManifest(
        skill_id="skyscanner-flight", domains=["flight"],
        capabilities={"search": True, "detail": True},
        health="DEGRADED", cost=0.3, trust=0.8))
    res = CapabilityResolver(reg)
    picked = res.resolve(domain="flight", capability="search")
    assert picked == "ctrip-flight"  # HEALTHY 优先于 DEGRADED


def test_resolver_considers_cost_when_same_health(tmp_path: Path) -> None:
    from universal_agent.registry.skills.resolver import CapabilityResolver
    from universal_agent.registry.registry import SkillRegistry

    reg = SkillRegistry()
    reg.register_skill(SkillManifest(
        skill_id="a", domains=["flight"], capabilities={"search": True},
        health="HEALTHY", cost=0.9, trust=0.5))
    reg.register_skill(SkillManifest(
        skill_id="b", domains=["flight"], capabilities={"search": True},
        health="HEALTHY", cost=0.2, trust=0.6))
    res = CapabilityResolver(reg)
    assert res.resolve(domain="flight", capability="search") == "b"  # 更便宜


def test_resolver_fail_closed_when_none(tmp_path: Path) -> None:
    from universal_agent.registry.skills.resolver import CapabilityResolver, NoSkillAvailable
    from universal_agent.registry.registry import SkillRegistry

    reg = SkillRegistry()
    res = CapabilityResolver(reg)
    with pytest.raises(NoSkillAvailable):
        res.resolve(domain="flight", capability="search")


def test_skill_does_not_execute_directly(tmp_path: Path) -> None:
    """高危 execute 不在 SkillProtocol 上（只经 ActionGateway）。"""
    from universal_agent.registry.skills.protocol import SkillProtocol
    assert not hasattr(SkillProtocol, "execute")
