"""Action Gateway (§35, §36, §37, §38, §39, §40).

All external side effects must pass through here (RULE 6). V1 only opens
L0_SCAN and L1_RECOMMEND. L2+ interfaces exist but are hard-blocked until
approval/idempotency/slippage/audit are fully stable.

Domain/Skill can only build ActionPlan; nothing executes directly (§36).
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from ...core.contracts import (
    ActionIntent,
    ActionLevel,
    ActionResult,
    Reversibility,
)
from ...registry import CapabilityDenied, SkillRegistry

log = logging.getLogger("ua.actions.gateway")

#: levels that are open in V1
OPEN_LEVELS = {ActionLevel.L0_SCAN, ActionLevel.L1_RECOMMEND}

#: levels that must not be executed until risk controls are stable
BLOCKED_LEVELS = {ActionLevel.L2_PREPARE, ActionLevel.L3_CONFIRM, ActionLevel.L4_EXECUTE}


class ActionGateway:
    def __init__(self, skill_registry: Optional[SkillRegistry] = None) -> None:
        self.skill_registry = skill_registry or SkillRegistry()
        self._executed: List[ActionResult] = []

    def check_intent(self, intent: ActionIntent) -> None:
        """Preflight checks — throws on any violation (no side effect yet)."""
        if intent.level in BLOCKED_LEVELS:
            raise CapabilityDenied(
                f"Action level {intent.level.value} is blocked in V1 "
                "(approval/idempotency/slippage/audit not yet fully stable)")
        if intent.level not in OPEN_LEVELS:
            raise CapabilityDenied(f"Unknown action level: {intent.level.value}")
        if not intent.idempotency_key:
            raise CapabilityDenied("idempotency_key is required (§38)")
        if intent.reversibility == Reversibility.IRREVERSIBLE:
            raise CapabilityDenied(
                "IRREVERSIBLE actions are not allowed until L3/L4 gates are enabled")
        if intent.level == ActionLevel.L1_RECOMMEND:
            if intent.max_slippage_cny is None and intent.max_slippage_percent is None:
                # not fatal — recommend only
                pass

    def execute(self, intent: ActionIntent, skill_id: Optional[str] = None) -> ActionResult:
        """Execute a single intent through the gateway (L0/L1 only in V1)."""
        self.check_intent(intent)
        if skill_id is not None and self.skill_registry is not None:
            # RULE 6 / §43: even prepare_order must be capability-granted
            if intent.action in ("prepare_order", "execute_order"):
                self.skill_registry.assert_capability(skill_id, intent.action)
        result = ActionResult(
            intent_id=intent.intent_id,
            plan_id="__direct__",
            status="EXECUTED",
            detail={"level": intent.level.value, "action": intent.action},
        )
        self._executed.append(result)
        return result

    def history(self) -> List[ActionResult]:
        return list(self._executed)
