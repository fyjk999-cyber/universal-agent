"""ControlledExecutor — DEPRECATED wrapper（P0.9-5）。

L3/L4 唯一正式执行路径是 TransactionExecutor。
本类保留为向后兼容的薄封装：内部委托 TransactionExecutor，
不再维护第二套安全实现（防止双路径分叉导致安全缺口）。
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

from ...core.contracts import ActionIntent, ActionLevel
from ...observability.audit import AuditLog
from ..approval import ApprovalInbox
from ..compensation import CompensationManager
from ..idempotency import IdempotencyStore
from ..slippage import SlippageGuard
from ..policy import KillSwitch, PolicyEngine
from .transaction import TransactionExecutor, TxOutcome

log = logging.getLogger("ua.actions.execute")


class ExecOutcome(TxOutcome):
    """兼容旧返回结构（本质是 TxOutcome）。"""


class ControlledExecutor:
    """[DEPRECATED] 委托 TransactionExecutor；勿用于新代码。"""

    def __init__(self, *, killswitch: KillSwitch, policy: PolicyEngine,
                 idempotency: IdempotencyStore, approvals: ApprovalInbox,
                 audit: AuditLog,
                 slippage: Optional[SlippageGuard] = None,
                 compensation: Optional[CompensationManager] = None,
                 reconcile_fn: Optional[Callable[[str], Dict[str, Any]]] = None) -> None:
        self._inner = TransactionExecutor(
            killswitch=killswitch, policy=policy, idempotency=idempotency,
            audit=audit, slippage=slippage, compensation=compensation,
            reconcile_fn=reconcile_fn)
        self.approvals = approvals
        self.audit = audit
        self.idempotency = idempotency
        self.killswitch = killswitch
        self.policy = policy

    def set_executor(self, fn: Callable[[ActionIntent], tuple]) -> None:
        self._inner.set_executor(fn)

    def execute(self, intent: ActionIntent,
                confirmed_price: Optional[float] = None,
                actor: str = "user") -> ExecOutcome:
        """委托 TransactionExecutor（唯一正式 L3/L4 路径）。

        顺序：KillSwitch → Policy deny → Approval → TransactionExecutor。
        """
        # 1) Kill Switch
        try:
            self.killswitch.assert_alive()
        except Exception as exc:  # noqa: BLE001
            return ExecOutcome(status="KILLED", state=None,
                               detail={"reason": str(exc)})

        # 2) Policy deny（默认 deny 时直接 BLOCKED）
        try:
            rule = self.policy.check(action=intent.action, level=intent.level.value,
                                     amount_cny=confirmed_price)
        except Exception as exc:  # noqa: BLE001
            return ExecOutcome(status="BLOCKED", state=None,
                               detail={"reason": str(exc)})

        # 3) Slippage 预检（P0.9-5: 滑移超限先 BLOCK；无快照也 BLOCK）
        if intent.approved_price_cny is None:
            return ExecOutcome(status="BLOCKED", state=None,
                               detail={"reason": "no approved price snapshot (P0.3)"})
        if confirmed_price is not None:
            from ...actions.slippage import SlippageGuard
            g = SlippageGuard().check(intent.approved_price_cny, confirmed_price,
                                      max_cny=intent.max_slippage_cny,
                                      max_percent=intent.max_slippage_percent)
            if not g.allowed:
                return ExecOutcome(status="BLOCKED", state=None,
                                   detail={"reason": g.reason})

        # 4) Approval（需审批时）
        if rule.requires_approval:
            approved_rec = self.approvals.find_by_payload(
                "intent_id", intent.intent_id, status="APPROVED")
            if approved_rec is None:
                pending = [a for a in self.approvals.pending()
                           if a.get("payload", {}).get("intent_id") == intent.intent_id]
                if not pending:
                    approval = self.approvals.request(
                        approval_type=_type(intent), title=f"execute {intent.action}",
                        payload={"intent_id": intent.intent_id,
                                 "confirmed_price": confirmed_price})
                    return ExecOutcome(status="NEEDS_APPROVAL", state=None,
                                       detail={"approval_id": approval["approval_id"]})
                return ExecOutcome(status="NEEDS_APPROVAL", state=None,
                                   detail={"approval_id": pending[0]["approval_id"]})

        # 4) 委托 TransactionExecutor（唯一正式路径）
        tx = self._inner.execute(intent, actual_price=confirmed_price, actor=actor)
        return ExecOutcome(status=tx.status, state=tx.state,
                           detail=tx.detail, compensation_status=tx.compensation_status)


def _type(intent: ActionIntent) -> str:
    if "job" in intent.action or "application" in intent.action:
        return "job_application"
    if "order" in intent.action:
        return "order"
    return "purchase"
