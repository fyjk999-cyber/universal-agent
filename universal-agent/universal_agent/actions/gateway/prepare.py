"""Action Preparation pipeline (§65) — PREPARE only, never COMMIT.

L2_PREPARE: 机票→确认页 / Job→提交前 / 购物→结算页.
不真正 Commit：PREPARE 返回可执行计划 + 审批请求，不触发任何外部副作用.

风险控制骨架（§37/§38/§39/§41/§50）全部接入本管线：
  Preflight → Idempotency → Slippage → Approval → Audit
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ...core.contracts import ActionIntent, ActionLevel, Reversibility
from ..approval import ApprovalInbox
from ..idempotency import IdempotencyStore
from ..slippage import SlippageGuard
from ...observability.audit import AuditLog
from ...registry import CapabilityDenied, SkillRegistry

log = logging.getLogger("ua.actions.prepare")


@dataclass
class PrepareOutcome:
    intent: ActionIntent
    status: str  # PREPARED | BLOCKED | NEEDS_APPROVAL | DUPLICATE
    approval: Optional[Dict[str, Any]] = None
    audit_ref: Optional[str] = None
    detail: Dict[str, Any] = field(default_factory=dict)

    def summary(self) -> Dict[str, Any]:
        return {"intent": self.intent.intent_id, "action": self.intent.action,
                "status": self.status, "level": self.intent.level.value}


class ActionPreparer:
    """Runs PREPARE intents through the risk-control skeleton.

    PREPARE itself is side-effect-free: it only validates + books approval.
    The actual preparation (navigating to confirmation page) would be executed
    by a Skill through an Adapter in a later step — here it's the plan only.
    """

    def __init__(self, *, idempotency: IdempotencyStore,
                 approvals: ApprovalInbox,
                 audit: AuditLog,
                 slippage: Optional[SlippageGuard] = None,
                 skill_registry: Optional[SkillRegistry] = None) -> None:
        self.idempotency = idempotency
        self.approvals = approvals
        self.audit = audit
        self.slippage = slippage or SlippageGuard()
        self.skill_registry = skill_registry or SkillRegistry()

    def prepare(self, intent: ActionIntent,
                confirmed_price: Optional[float] = None,
                skill_id: Optional[str] = None,
                actor: str = "user") -> PrepareOutcome:
        """PREPARE 一个 intent（只到确认页/提交前，不 Commit）。"""
        # ---- Preflight (§37) ----
        if intent.level != ActionLevel.L2_PREPARE:
            raise CapabilityDenied(
                f"prepare() only accepts L2_PREPARE, got {intent.level.value}")
        if not intent.idempotency_key:
            raise CapabilityDenied("idempotency_key is required (§38)")
        if intent.reversibility == Reversibility.IRREVERSIBLE:
            raise CapabilityDenied(
                "IRREVERSIBLE actions cannot PREPARE until L3/L4 gates are enabled")

        # ---- Idempotency (§38) ----
        existing = self.idempotency.get(intent.idempotency_key)
        if existing is not None:
            return PrepareOutcome(intent=intent, status="DUPLICATE",
                                  detail={"existing": existing["result"]})

        # ---- Slippage (§39) ----
        if confirmed_price is not None:
            guard = self.slippage.check(
                confirmed_price, confirmed_price,
                max_cny=intent.max_slippage_cny,
                max_percent=intent.max_slippage_percent)
            if not guard.allowed:
                raise CapabilityDenied(f"slippage preflight failed: {guard.reason}")

        # ---- Skill capability (§43) ----
        if skill_id is not None and intent.action in ("prepare_order", "execute_order"):
            self.skill_registry.assert_capability(skill_id, "prepare_order")

        # ---- Approval (§41) ----
        approval = self.approvals.request(
            approval_type=_approval_type(intent),
            title=f"{intent.action}: {intent.target_key}",
            payload={"confirmed_price": confirmed_price,
                     "reversibility": intent.reversibility.value},
            task_id=intent.task_id if hasattr(intent, "task_id") else None,
        )

        # ---- Audit (§50) ----
        entry = self.audit.record(
            actor=actor,
            action=f"PREPARE::{intent.action}",
            reason="action preparation to confirmation step",
            based_on={"intent_id": intent.intent_id,
                      "idempotency_key": intent.idempotency_key},
            approved=None,
            result={"approval_id": approval["approval_id"]},
        )

        # 登记 idempotency（PREPARE 完成 = 幂等完成）
        self.idempotency.register(
            intent.idempotency_key, action=intent.action,
            target_key=intent.target_key or "",
            result={"status": "PREPARED", "approval_id": approval["approval_id"]})

        return PrepareOutcome(intent=intent, status="PREPARED",
                              approval=approval,
                              audit_ref=entry["ts"])


def _approval_type(intent: ActionIntent) -> str:
    if "job" in intent.action or "application" in intent.action:
        return "job_application"
    if "order" in intent.action:
        return "order"
    return "purchase"
