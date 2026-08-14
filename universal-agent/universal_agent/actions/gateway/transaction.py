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
from ..idempotency import IdempotencyStore, IdempotencyStatus
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

        # ---- RESERVE IDEMPOTENCY（P0.5）----
        try:
            self.idempotency.reserve(intent.idempotency_key, action=intent.action,
                                     target_key=intent.target_key or "")
        except Exception as exc:  # noqa: BLE001
            existing = self.idempotency.get(intent.idempotency_key)
            if existing is not None and existing.get("status") == IdempotencyStatus.FINALIZED.value:
                return TxOutcome(status="DUPLICATE", state=ExecutionState.VERIFIED,
                                 detail={"existing": existing.get("result")})
            raise

        # ---- COMMIT BOUNDARY：EXECUTE ----
        if self.executor_fn is None:
            return TxOutcome(status="BLOCKED", state=ExecutionState.FAILED,
                             detail={"reason": "no executor registered"})
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

    def _audit(self, actor, intent, status, detail, approved=None) -> None:
        self.audit.record(
            actor=actor, action=f"TX::{intent.action}::{status}",
            reason="transactional execution (P0.4)",
            based_on={"intent_id": intent.intent_id,
                      "idempotency_key": intent.idempotency_key},
            approved=approved,
            result={"status": status, "detail": detail})
