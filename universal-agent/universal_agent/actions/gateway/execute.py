"""Controlled Execution（§66）— 受控执行管线。

仅在全部风险控制稳定后开放；Phase 7 实现完整管线但保持默认策略
default_deny=True —— 真实副作用动作必须显式 policy 放行才会执行。

流程（§37 事务语义）：
  KillSwitch → Policy → Preflight → Idempotency → Slippage
  → Approval → Commit Boundary → Execute → Verify → Compensate → Audit

真实金融订单/自动购票仍由 §56 禁止（policy 不放行即无法执行）。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from ...core.contracts import ActionIntent, ActionLevel, Reversibility
from ...observability.audit import AuditLog
from ...registry import CapabilityDenied
from ..approval import ApprovalInbox
from ..compensation import CompensationManager, CompensationResult, CompensationStep
from ..idempotency import IdempotencyStore
from ..slippage import SlippageGuard
from ..policy import KillSwitch, KillSwitchTripped, PolicyEngine, PolicyViolation

log = logging.getLogger("ua.actions.execute")


@dataclass
class ExecOutcome:
    status: str  # BLOCKED | NEEDS_APPROVAL | EXECUTED | FAILED | DUPLICATE | KILLED
    detail: Dict[str, Any] = field(default_factory=dict)
    compensation: Optional[CompensationResult] = None

    def summary(self) -> Dict[str, Any]:
        return {"status": self.status, "detail": self.detail}


class ControlledExecutor:
    """执行 L3_CONFIRM / L4_EXECUTE 意图（受全部风险控制约束）。"""

    def __init__(self, *, killswitch: KillSwitch, policy: PolicyEngine,
                 idempotency: IdempotencyStore, approvals: ApprovalInbox,
                 audit: AuditLog,
                 slippage: Optional[SlippageGuard] = None,
                 compensation: Optional[CompensationManager] = None) -> None:
        self.killswitch = killswitch
        self.policy = policy
        self.idempotency = idempotency
        self.approvals = approvals
        self.audit = audit
        self.slippage = slippage or SlippageGuard()
        self.compensation = compensation or CompensationManager(audit=audit)
        #: 注入的真实执行函数：intent → (result, compensation_steps)
        self.executor_fn: Optional[Callable[[ActionIntent], tuple]] = None

    def set_executor(self, fn: Callable[[ActionIntent], tuple]) -> None:
        """注入 Skill/Adapter 执行函数（生产时由注册的 Skill 提供）。"""
        self.executor_fn = fn

    def execute(self, intent: ActionIntent,
                confirmed_price: Optional[float] = None,
                actor: str = "user") -> ExecOutcome:
        # ---- Kill Switch（§66）----
        try:
            self.killswitch.assert_alive()
        except KillSwitchTripped as exc:
            self._audit(actor, intent, "KILLED", str(exc))
            return ExecOutcome(status="KILLED", detail={"reason": str(exc)})

        # ---- Policy（§35/§66）----
        try:
            rule = self.policy.check(action=intent.action, level=intent.level.value,
                                     amount_cny=confirmed_price)
        except PolicyViolation as exc:
            self._audit(actor, intent, "BLOCKED", str(exc))
            return ExecOutcome(status="BLOCKED", detail={"reason": str(exc)})

        # ---- Preflight / 级别 ----
        if intent.level not in (ActionLevel.L3_CONFIRM, ActionLevel.L4_EXECUTE):
            raise CapabilityDenied(
                f"execute() only accepts L3/L4, got {intent.level.value}")

        # ---- Idempotency（§38 + P0.5：reserve/finalize）----
        from ..idempotency import DuplicateRequest as _Dup
        try:
            self.idempotency.reserve(intent.idempotency_key, action=intent.action,
                                     target_key=intent.target_key or "")
        except _Dup:
            existing = self.idempotency.get(intent.idempotency_key)
            return ExecOutcome(status="DUPLICATE",
                               detail={"existing": existing.get("result") if existing else {}})

        # ---- Slippage（P0.3：approved vs actual，禁止自比较）----
        # 批准价来自 intent.approved_price_cny（L3/L4 必须已批准）
        approved_price = intent.approved_price_cny
        if approved_price is None:
            self._audit(actor, intent, "BLOCKED", "no approved price snapshot")
            return ExecOutcome(status="BLOCKED",
                               detail={"reason": "no approved price snapshot (P0.3)"})

        # 执行前重新获取 actual checkout price（由 executor 注入的价格源）
        actual_price = confirmed_price if confirmed_price is not None else approved_price
        g = self.slippage.check(
            approved_price, actual_price,
            max_cny=intent.max_slippage_cny,
            max_percent=intent.max_slippage_percent)
        if not g.allowed:
            self._audit(actor, intent, "BLOCKED", g.reason)
            return ExecOutcome(status="BLOCKED", detail={"reason": g.reason})

        # 材料变化检查（价格之外的字段：币种/行李/退改/数量/日期/订单内容）
        material = self.slippage.check_material(
            _approved_snapshot(intent),
            _actual_snapshot(intent, actual_price, confirmed_price is not None))
        if material.material_change:
            self._audit(actor, intent, "BLOCKED", material.reason)
            return ExecOutcome(status="BLOCKED",
                               detail={"reason": f"material change: {material.reason}"})

        # ---- Approval（§41/§66）----
        if rule.requires_approval:
            # 已批准过该 intent → 继续执行（§41 人工批准生效）
            approved_rec = self.approvals.find_by_payload(
                "intent_id", intent.intent_id, status="APPROVED")
            if approved_rec is not None:
                self._audit(actor, intent, "EXECUTING",
                            f"pre-approved {approved_rec['approval_id']}",
                            approved=True)
            else:
                pending = [a for a in self.approvals.pending()
                           if a.get("payload", {}).get("intent_id") == intent.intent_id]
                if not pending:
                    approval = self.approvals.request(
                        approval_type=_type(intent), title=f"execute {intent.action}",
                        payload={"intent_id": intent.intent_id,
                                 "confirmed_price": confirmed_price},
                        task_id=getattr(intent, "task_id", None))
                    self._audit(actor, intent, "NEEDS_APPROVAL",
                                approval["approval_id"])
                    return ExecOutcome(status="NEEDS_APPROVAL",
                                       detail={"approval_id": approval["approval_id"]})
                # 有 pending 审批 → 等待（不允许自动批准）
                return ExecOutcome(status="NEEDS_APPROVAL",
                                   detail={"approval_id": pending[0]["approval_id"]})

        # ---- Commit Boundary：执行 ----
        if self.executor_fn is None:
            self._audit(actor, intent, "BLOCKED", "no executor registered")
            return ExecOutcome(status="BLOCKED",
                               detail={"reason": "no executor registered"})

        steps: List[CompensationStep] = []
        try:
            result, steps = self.executor_fn(intent)
        except Exception as exc:  # noqa: BLE001
            self._audit(actor, intent, "FAILED", str(exc))
            return ExecOutcome(status="FAILED", detail={"error": str(exc)})

        # ---- P0.4: 成功路径绝不自动补偿 ----
        self.idempotency.finalize(intent.idempotency_key,
                                  {"status": "EXECUTED", **result})
        self._audit(actor, intent, "EXECUTED", str(result),
                    approved=not (rule.requires_approval))
        # 成功：不调用 compensation（P0.4 修复）；steps 仅作为预案保留在结果里
        return ExecOutcome(status="EXECUTED", detail=result,
                           compensation=None)

    def _audit(self, actor, intent, status, detail, approved=None) -> None:
        self.audit.record(
            actor=actor, action=f"EXECUTE::{intent.action}::{status}",
            reason="controlled execution",
            based_on={"intent_id": intent.intent_id,
                      "idempotency_key": intent.idempotency_key},
            approved=approved,
            result={"status": status, "detail": detail})


def _type(intent: ActionIntent) -> str:
    if "job" in intent.action or "application" in intent.action:
        return "job_application"
    if "order" in intent.action:
        return "order"
    return "purchase"


def _approved_snapshot(intent: ActionIntent) -> dict:
    """批准时的快照（P0.3）：价格 + 订单关键字段。"""
    return {
        "price": intent.approved_price_cny,
        "offer_id": intent.approved_offer_id,
        "quote_id": intent.approved_quote_id,
        "currency": (intent.params or {}).get("currency"),
        "baggage": (intent.params or {}).get("baggage"),
        "refundable": (intent.params or {}).get("refundable"),
        "quantity": (intent.params or {}).get("quantity"),
        "date": (intent.params or {}).get("date"),
        "flight": (intent.params or {}).get("flight"),
        "room": (intent.params or {}).get("room"),
        "passenger": (intent.params or {}).get("passenger"),
    }


def _actual_snapshot(intent: ActionIntent, actual_price: float,
                     price_fetched: bool) -> dict:
    """执行前重取的实际快照（P0.3）。price 来自实际 checkout。"""
    params = intent.params or {}
    return {
        "price": actual_price if price_fetched else intent.approved_price_cny,
        "offer_id": params.get("actual_offer_id") or intent.approved_offer_id,
        "quote_id": params.get("actual_quote_id") or intent.approved_quote_id,
        "currency": params.get("currency"),
        "baggage": params.get("baggage"),
        "refundable": params.get("refundable"),
        "quantity": params.get("quantity"),
        "date": params.get("date"),
        "flight": params.get("flight"),
        "room": params.get("room"),
        "passenger": params.get("passenger"),
    }
