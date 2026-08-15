"""P1.1e — Transaction external-call ambiguity：网络异常不得自动假设 FAILED。

指令要求：
  external execute → timeout/error → UNKNOWN（不标 FAILED_SAFE_TO_RETRY）
  → reconcile：CONFIRMED→FINALIZED / NOT_FOUND→SAFE_TO_RETRY / UNKNOWN→HUMAN
"""
from __future__ import annotations

from pathlib import Path

import pytest

from universal_agent.actions.gateway.transaction import TransactionExecutor
from universal_agent.actions.idempotency import IdempotencyStatus, IdempotencyStore
from universal_agent.actions.policy import KillSwitch, PolicyEngine
from universal_agent.core.contracts import ActionIntent, ActionLevel, ExecutionState, Reversibility
from universal_agent.observability.audit import AuditLog


def _intent(key: str = "k1") -> ActionIntent:
    return ActionIntent(
        intent_id=f"i-{key}", action="execute_order", target_key="c1",
        idempotency_key=key, level=ActionLevel.L4_EXECUTE,
        reversibility=Reversibility.FULL, max_slippage_cny=100,
        approved_price_cny=4380.0,
    )


def _tx(tmp_path: Path, reconcile_fn=None) -> TransactionExecutor:
    return TransactionExecutor(
        killswitch=KillSwitch(tmp_path / "ks.json"),
        policy=PolicyEngine(default={"default_deny": False, "rules": [
            {"action": "execute_order", "level": "L4_EXECUTE", "requires_approval": False}]}),
        idempotency=IdempotencyStore(tmp_path / "idem"),
        audit=AuditLog(tmp_path / "audit"),
        reconcile_fn=reconcile_fn,
    )


class _NetworkTimeout(Exception):
    pass


def test_external_timeout_is_unknown_not_failed(tmp_path: Path) -> None:
    """external 超时 → UNKNOWN（禁止自动 FAILED_SAFE_TO_RETRY）。"""
    tx = _tx(tmp_path)

    def boom(intent):
        raise _NetworkTimeout("platform timeout after commit")

    tx.set_executor(boom)
    out = tx.execute(_intent())
    # 状态必须是 UNKNOWN（可 reconcile），而不是 FAILED_SAFE_TO_RETRY
    assert out.state in (ExecutionState.UNKNOWN, ExecutionState.COMPENSATED)
    assert out.status not in ("FAILED_SAFE_TO_RETRY",)
    # idempotency 记录保留（不丢，供 reconcile 查询）
    rec = tx.idempotency.get("k1")
    assert rec is not None


def test_reconcile_confirmed_prevents_duplicate(tmp_path: Path) -> None:
    """reconcile CONFIRMED → FINALIZED（防二次执行）。"""
    tx = _tx(tmp_path, reconcile_fn=lambda key: {"outcome": "CONFIRMED"})
    # 模拟 crash 残留：先 reserve + mark_committed
    tx.idempotency.reserve("k2", action="execute_order", target_key="c1")
    tx.idempotency.mark_committed("k2")
    out = tx.reconcile(_intent("k2"))
    assert out.status == "DUPLICATE"
    assert tx.idempotency.get("k2")["status"] == IdempotencyStatus.FINALIZED.value


def test_reconcile_not_found_safe_to_retry(tmp_path: Path) -> None:
    """reconcile NOT_FOUND → SAFE_TO_RETRY。"""
    tx = _tx(tmp_path, reconcile_fn=lambda key: {"outcome": "NOT_FOUND"})
    tx.idempotency.reserve("k3", action="execute_order", target_key="c1")
    tx.idempotency.mark_committed("k3")
    out = tx.reconcile(_intent("k3"))
    assert out.status == "SAFE_TO_RETRY"


def test_reconcile_unknown_requires_human(tmp_path: Path) -> None:
    """reconcile UNKNOWN → 保持 UNKNOWN（需人工，不自动重试）。"""
    tx = _tx(tmp_path, reconcile_fn=lambda key: {"outcome": "UNKNOWN"})
    tx.idempotency.reserve("k4", action="execute_order", target_key="c1")
    tx.idempotency.mark_committed("k4")
    out = tx.reconcile(_intent("k4"))
    assert out.status in ("UNKNOWN", "RECONCILE_REQUIRED", "RECONCILE_UNKNOWN")
    assert out.state == ExecutionState.UNKNOWN
