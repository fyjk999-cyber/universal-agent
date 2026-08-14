"""Action Gateway tests (§35, §36, §43)."""
from __future__ import annotations

import pytest

from universal_agent.actions import ActionGateway
from universal_agent.core.contracts import (
    ActionIntent,
    ActionLevel,
    Reversibility,
    SkillManifest,
)
from universal_agent.registry import CapabilityDenied, SkillRegistry


def _intent(level: ActionLevel = ActionLevel.L1_RECOMMEND, **kw) -> ActionIntent:
    defaults = dict(intent_id="i1", action="recommend", idempotency_key="k1",
                    level=level, reversibility=Reversibility.FULL)
    defaults.update(kw)
    return ActionIntent(**defaults)


class TestActionGateway:
    def test_l1_recommend_allowed(self):
        gw = ActionGateway()
        res = gw.execute(_intent())
        assert res.status == "EXECUTED"

    def test_l0_scan_allowed(self):
        gw = ActionGateway()
        res = gw.execute(_intent(level=ActionLevel.L0_SCAN, action="scan"))
        assert res.status == "EXECUTED"

    def test_l2_blocked_in_v1(self):
        gw = ActionGateway()
        with pytest.raises(CapabilityDenied):
            gw.execute(_intent(level=ActionLevel.L2_PREPARE, action="prepare_order"))

    def test_l4_execute_blocked_in_v1(self):
        gw = ActionGateway()
        with pytest.raises(CapabilityDenied):
            gw.execute(_intent(level=ActionLevel.L4_EXECUTE, action="execute_order"))

    def test_idempotency_key_required(self):
        gw = ActionGateway()
        with pytest.raises(CapabilityDenied):
            gw.execute(_intent(idempotency_key=""))

    def test_irreversible_rejected(self):
        gw = ActionGateway()
        with pytest.raises(CapabilityDenied):
            gw.execute(_intent(reversibility=Reversibility.IRREVERSIBLE))

    def test_skill_capability_enforced(self):
        reg = SkillRegistry()
        reg.register_skill(SkillManifest(
            skill_id="ctrip.flight", domains=["flight"],
            capabilities={"search": True, "prepare_order": False},
        ))
        gw = ActionGateway(skill_registry=reg)
        with pytest.raises(CapabilityDenied):
            # §43: code calling execute_order must be rejected by registry
            gw.execute(_intent(action="execute_order", level=ActionLevel.L4_EXECUTE),
                       skill_id="ctrip.flight")
