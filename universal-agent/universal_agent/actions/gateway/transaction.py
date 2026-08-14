"""P0.4 事务执行协调器 — 成功路径绝不自动补偿。

正确事务模型：
  PREPARE → PRE-FLIGHT → RESERVE IDEMPOTENCY → COMMIT BOUNDARY
  → EXECUTE → VERIFY
  VERIFY SUCCESS → FINALIZE → NO COMPENSATION
  VERIFY FAILURE → COMPENSATION
  EXECUTE PARTIAL FAILURE → COMPENSATION
  EXECUTE UNKNOWN → RECONCILIATION → 再决定 compensation

ExecutionState 状态机贯穿整个流程；补偿仅在 VERIFY FAILURE /
PARTIAL FAILURE / 决策后的 UNKNOWN 时触发。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from ...core.contracts import ActionIntent, ExecutionState, Reversibility
from ...observability.audit import AuditLog
from ..compensation import CompensationManager, CompensationStep
from ..idempotency import DuplicateRequest, IdempotencyStatus, IdempotencyStore
from ..slippage import SlippageGuard
from ..policy import KillSwitch, KillSwitchTripped, PolicyEngine, PolicyViolation

log = logging.getLogger("ua.actions.tx")


@dataclass
class TxOutcome:
    status: str  # EXECUTED | FAILED | COMPENSATED | BLOCKED | KILLED | UNKNOWN
    state: ExecutionState
    detail: Dict[str, Any] = field(default_factory=dict)
    compensation_status: Optional[str] = None  # NOOP/COMPENSATED/PARTIAL/FAILED


class TransactionExecutor:
    """P0.4 事务语义的执行器。"""

    def __init__(self, *, killswitch: KillSwitch, policy: PolicyEngine,
                 idempotency: IdempotencyStore,
                 audit: AuditLog,
                 slippage: Optional[SlippageGuard] = None,
                 compensation: Optional[CompensationManager] = None,
                 reconcile_fn: Optional[Callable[[str], Dict[str, Any]]] = None) -> None:
        self.killswitch = killswitch
        self.policy = policy
        self.idempotency = idempotency
        self.audit = audit
        self.slippage = slippage or SlippageGuard()
        self.compensation = compensation or CompensationManager(audit=audit)
        self.reconcile_fn = reconcile_fn
        self.executor_fn: Optional[Callable[[ActionIntent], tuple]] = None

    def set_executor(self, fn: Callable[[ActionIntent], tuple]) -> None:
        self.executor_fn = fn

    def execute(self, intent: ActionIntent,
                actual_price: Optional[float] = None,
                actor: str = "user") -> TxOutcome:
        # ---- Kill Switch ----
        try:
            self.killswitch.assert_alive()
        except KillSwitchTripped as exc:
            return TxOutcome(status="KILLED", state=ExecutionState.FAILED,
                             detail={"reason": str(exc)})

        # ---- Policy ----
        try:
            rule = self.policy.check(action=intent.action, level=intent.level.value,
                                     amount_cny=actual_price)
        except PolicyViolation as exc:
            return TxOutcome(status="BLOCKED", state=ExecutionState.FAILED,
                             detail={"reason": str(exc)})

        # ---- PRE-FLIGHT（P0.3 approved vs actual）----
        approved = intent.approved_price_cny
        if approved is None:
            return TxOutcome(status="BLOCKED", state=ExecutionState.FAILED,
                             detail={"reason": "no approved price snapshot (P0.3)"})
        if actual_price is not None:
            g = self.slippage.check(approved, actual_price,
                                    max_cny=intent.max_slippage_cny,
                                    max_percent=intent.max_slippage_percent)
            if not g.allowed:
                return TxOutcome(status="BLOCKED", state=ExecutionState.FAILED,
                                 detail={"reason": g.reason})

        # ---- P0.9-6: Approval Snapshot 完整性检查 ----
        snapshot_err = self._check_approval_snapshot(intent)
        if snapshot_err:
            return TxOutcome(status="REAPPROVAL_REQUIRED",
                             state=ExecutionState.FAILED,
                             detail={"reason": snapshot_err})

        # ---- RESERVE IDEMPOTENCY（P0.5 + P0.9-5 Commit Boundary）----
        pre_existing = self.idempotency.get(intent.idempotency_key)
        try:
            reserved = self.idempotency.reserve(intent.idempotency_key,
                                                action=intent.action,
                                                target_key=intent.target_key or "")
        except DuplicateRequest:
            existing = self.idempotency.get(intent.idempotency_key)
            return TxOutcome(status="DUPLICATE", state=ExecutionState.VERIFIED,
                             detail={"existing": existing.get("result") if existing else {}})

        # P0.9-5: key 已存在（非首次）→ 不得直接执行，必须 reconcile
        #（crash ambiguity：RESERVED 残留 / COMMITTED / UNKNOWN）
        if pre_existing is not None:
            rec_status = pre_existing.get("status")
            return TxOutcome(
                status="RECONCILE_REQUIRED", state=ExecutionState.UNKNOWN,
                detail={"idempotency_status": rec_status,
                        "reason": "existing idempotency state: must reconcile before retry (P0.9-5)"})

        # 首次 reserve → 继续

        # ---- COMMIT BOUNDARY：标记 COMMITTING ----
        if self.executor_fn is None:
            return TxOutcome(status="BLOCKED", state=ExecutionState.FAILED,
                             detail={"reason": "no executor registered"})
        # 进入不可逆 commit 前标记 COMMITTED（crash 时状态为 COMMITTED → 需 reconcile）
        self.idempotency.mark_committed(intent.idempotency_key)
        state = ExecutionState.COMMITTING
        steps: List[CompensationStep] = []
        try:
            result, steps = self.executor_fn(intent)
            state = ExecutionState.COMMITTED
        except Exception as exc:  # noqa: BLE001
            # EXECUTE 失败（可能部分副作用已发生）→ 进入 UNKNOWN/补偿判定
            state = ExecutionState.UNKNOWN
            self._audit(actor, intent, "UNKNOWN", str(exc))
            comp = self.compensation.compensate(
                steps, failure_stage="execute", reversibility=intent.reversibility,
                task_id=getattr(intent, "task_id", None))
            self.idempotency.finalize(intent.idempotency_key,
                                      {"status": "FAILED", "error": str(exc)},
                                      status=IdempotencyStatus.FAILED)
            return TxOutcome(status="COMPENSATED" if comp.status == "COMPENSATED" else "FAILED",
                             state=ExecutionState.COMPENSATED if comp.status == "COMPENSATED"
                             else ExecutionState.FAILED,
                             detail={"error": str(exc), "result": result if 'result' in dir() else {}},
                             compensation_status=comp.status)

        # ---- VERIFY ----
        state = ExecutionState.VERIFYING
        verified = self._verify(intent, result)
        if not verified:
            state = ExecutionState.FAILED
            comp = self.compensation.compensate(
                steps, failure_stage="verify", reversibility=intent.reversibility,
                task_id=getattr(intent, "task_id", None))
            self.idempotency.finalize(intent.idempotency_key,
                                      {"status": "FAILED", "verify": "failed"},
                                      status=IdempotencyStatus.FAILED)
            return TxOutcome(status="COMPENSATED" if comp.status == "COMPENSATED" else "FAILED",
                             state=ExecutionState.COMPENSATED if comp.status == "COMPENSATED"
                             else ExecutionState.FAILED,
                             detail={"verify": "failed"},
                             compensation_status=comp.status)

        # ---- VERIFY SUCCESS → FINALIZE → NO COMPENSATION（P0.4）----
        state = ExecutionState.VERIFIED
        self.idempotency.finalize(intent.idempotency_key,
                                  {"status": "EXECUTED", **result},
                                  status=IdempotencyStatus.FINALIZED)
        self._audit(actor, intent, "EXECUTED", str(result), approved=True)
        return TxOutcome(status="EXECUTED", state=ExecutionState.VERIFIED,
                         detail=result, compensation_status="NOOP")

    def _verify(self, intent: ActionIntent, result: Dict[str, Any]) -> bool:
        """验证执行结果（P0.4）。默认：executor 返回 ok=True 视为验证通过。"""
        return bool(result and result.get("ok", True))

    def reconcile(self, intent: ActionIntent, actor: str = "user") -> TxOutcome:
        """P0.9-5: 对 crash 残留（RESERVED/COMMITTED/UNKNOWN）查询平台真实状态。

        结果：
          CONFIRMED → FINALIZED（防重复执行）
          NOT_FOUND → FAILED_SAFE_TO_RETRY
          UNKNOWN   → 保持 UNKNOWN（不自动重试，需人工）
        """
        rec = self.idempotency.get(intent.idempotency_key)
        if rec is None:
            return TxOutcome(status="BLOCKED", state=ExecutionState.FAILED,
                             detail={"reason": "no idempotency record"})
        rec_status = rec.get("status")
        if rec_status == IdempotencyStatus.FINALIZED.value:
            return TxOutcome(status="DUPLICATE", state=ExecutionState.VERIFIED,
                             detail={"existing": rec.get("result")})

        if self.reconcile_fn is None:
            return TxOutcome(status="RECONCILE_REQUIRED",
                             state=ExecutionState.UNKNOWN,
                             detail={"reason": "no reconcile_fn registered; "
                                                "cannot determine platform state (P0.9-5)"})
        platform = self.reconcile_fn(intent.idempotency_key)
        outcome = platform.get("outcome", "UNKNOWN")
        if outcome == "CONFIRMED":
            self.idempotency.finalize(intent.idempotency_key,
                                      {"status": "EXECUTED", **platform},
                                      status=IdempotencyStatus.FINALIZED)
            self._audit(actor, intent, "RECONCILED_CONFIRMED", str(platform))
            return TxOutcome(status="DUPLICATE", state=ExecutionState.VERIFIED,
                             detail={"platform": platform, "prevented_duplicate": True})
        if outcome == "NOT_FOUND":
            self.idempotency.finalize(intent.idempotency_key,
                                      {"status": "NOT_CONFIRMED", **platform},
                                      status=IdempotencyStatus.FAILED)
            self._audit(actor, intent, "RECONCILED_SAFE_RETRY", str(platform))
            return TxOutcome(status="SAFE_TO_RETRY", state=ExecutionState.FAILED,
                             detail={"platform": platform})
        # UNKNOWN → 不自动重试
        self._audit(actor, intent, "RECONCILE_UNKNOWN", str(platform))
        return TxOutcome(status="RECONCILE_UNKNOWN", state=ExecutionState.UNKNOWN,
                         detail={"platform": platform,
                                 "reason": "platform state unknown; human review required"})

    def _check_approval_snapshot(self, intent: ActionIntent) -> Optional[str]:
        """P0.9-6: 审批快照完整性。返回错误原因（None = 通过）。

        检查：
          - approval_expires_at 未过期
          - approved_quote_id / approved_offer_id 与实际一致（params 传入）
          - 材料变化：offer 版本 / quote / 行李 / 退改 / 日期 / 数量 / 乘客 / 房型
        """
        from datetime import datetime, timezone

        # expiry
        if intent.approval_expires_at is not None:
            if intent.approval_expires_at.tzinfo is None:
                exp = intent.approval_expires_at.replace(tzinfo=timezone.utc)
            else:
                exp = intent.approval_expires_at
            if exp < datetime.now(timezone.utc):
                return f"approval expired at {intent.approval_expires_at}; reapproval required"

        params = intent.params or {}
        actual_offer = params.get("actual_offer_id")
        actual_quote = params.get("actual_quote_id")

        # offer/quote 一致性
        if intent.approved_offer_id and actual_offer \
                and intent.approved_offer_id != actual_offer:
            return (f"offer changed: approved {intent.approved_offer_id} "
                    f"!= actual {actual_offer}; reapproval required")
        if intent.approved_quote_id and actual_quote \
                and intent.approved_quote_id != actual_quote:
            return (f"quote changed: approved {intent.approved_quote_id} "
                    f"!= actual {actual_quote}; reapproval required")

        # 材料变化（订单内容字段）
        material_fields = ["baggage", "refundable", "date", "quantity",
                           "passenger", "room", "flight"]
        changed = [f for f in material_fields
                   if f in params and f"{params.get(f)}" != ""]
        for f in material_fields:
            approved_v = (intent.params or {}).get(f"approved_{f}")
            actual_v = params.get(f)
            if approved_v is not None and actual_v is not None and approved_v != actual_v:
                return (f"material change in {f}: approved {approved_v} "
                        f"!= actual {actual_v}; reapproval required")
        return None

    def _audit(self, actor, intent, status, detail, approved=None) -> None:
        self.audit.record(
            actor=actor, action=f"TX::{intent.action}::{status}",
            reason="transactional execution (P0.4)",
            based_on={"intent_id": intent.intent_id,
                      "idempotency_key": intent.idempotency_key},
            approved=approved,
            result={"status": status, "detail": detail})
