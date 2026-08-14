"""P0.4 + P0.5 回归测试：事务补偿 + Idempotency 状态机。

规则：
- test_success_never_compensates（成功绝不自动补偿）
- test_execute_failure_compensates
- test_verify_failure_compensates
- test_irreversible_never_fake_rolls_back
- test_partial_compensation
- test_compensation_failure_audited
- test_commit_crash_reconciliation（P0.5）
"""
from __future__ import annotations

from pathlib import Path

import pytest

from universal_agent.actions import (
    ApprovalInbox,
    CompensationManager,
    CompensationStep,
    IdempotencyStatus,
    IdempotencyStore,
    KillSwitch,
    PolicyEngine,
    TransactionExecutor,
)
from universal_agent.core.contracts import ActionIntent, ActionLevel, ExecutionState, Reversibility
from universal_agent.observability.audit import AuditLog


def _intent(**kw) -> ActionIntent:
    defaults = dict(
        intent_id="t1", action="execute_order", target_key="c1",
        idempotency_key="idem-t1", level=ActionLevel.L4_EXECUTE,
        reversibility=Reversibility.FULL, max_slippage_cny=100,
        approved_price_cny=4380.0,
    )
    defaults.update(kw)
    return ActionIntent(**defaults)


def _tx(tmp_path, policy=None) -> TransactionExecutor:
    return TransactionExecutor(
        killswitch=KillSwitch(tmp_path / "ks.json"),
        policy=policy or PolicyEngine(default={"default_deny": False, "rules": [
            {"action": "execute_order", "level": "L4_EXECUTE", "requires_approval": False}]}),
        idempotency=IdempotencyStore(tmp_path / "idem"),
        audit=AuditLog(tmp_path / "audit"),
    )


class TestSuccessNeverCompensates:
    def test_success_never_compensates(self, tmp_path):
        """P0.4 核心：成功执行绝不调用 compensation。"""
        ex = _tx(tmp_path)
        called = []

        def comp_step():
            called.append("revert")

        ex.compensation = CompensationManager(audit=ex.audit)
        ex.set_executor(lambda intent: ({"ok": True, "order": "o1"},
                                         [CompensationStep(name="s1", revert=comp_step)]))
        out = ex.execute(_intent(), actual_price=4380)
        assert out.status == "EXECUTED"
        assert out.compensation_status == "NOOP"
        assert called == []  # 补偿从未触发
        assert out.state == ExecutionState.VERIFIED


class TestFailureCompensates:
    def test_execute_failure_compensates(self, tmp_path):
        ex = _tx(tmp_path)
        reverted = []

        # executor 部分执行后抛异常（副作用已发生 → 补偿）
        def partial(intent):
            reverted.append("reserve")
            raise RuntimeError("platform down")

        ex.set_executor(partial)
        ex.compensation = CompensationManager(audit=ex.audit)
        out = ex.execute(_intent(), actual_price=4380)
        assert out.status in ("COMPENSATED", "FAILED")
        assert out.state in (ExecutionState.COMPENSATED, ExecutionState.FAILED)

    def test_verify_failure_compensates(self, tmp_path):
        ex = _tx(tmp_path)
        reverted = []
        ex.set_executor(lambda intent: ({"ok": False, "error": "verify failed"},  # verify 失败
                                         [CompensationStep(name="v", revert=lambda: reverted.append("v"))]))
        out = ex.execute(_intent(), actual_price=4380)
        assert out.status == "COMPENSATED"
        assert reverted == ["v"]

    def test_irreversible_never_fake_rolls_back(self, tmp_path):
        """IRREVERSIBLE → NOOP（绝不假装回滚）。"""
        ex = _tx(tmp_path)
        ex.set_executor(lambda intent: ({"ok": False}, []))
        out = ex.execute(_intent(reversibility=Reversibility.IRREVERSIBLE), actual_price=4380)
        # verify 失败但 IRREVERSIBLE → 无法补偿
        assert out.compensation_status in ("NOOP", None)

    def test_partial_compensation(self, tmp_path):
        ex = _tx(tmp_path)

        def bad_revert():
            raise RuntimeError("revert failed")

        steps = [
            CompensationStep(name="ok", revert=lambda: None),
            CompensationStep(name="bad", revert=bad_revert),
        ]
        ex.set_executor(lambda intent: ({"ok": False}, steps))
        out = ex.execute(_intent(), actual_price=4380)
        assert out.compensation_status == "PARTIAL"

    def test_compensation_failure_audited(self, tmp_path):
        ex = _tx(tmp_path)
        ex.set_executor(lambda intent: ({"ok": False},
                                         [CompensationStep(name="x", revert=lambda: (_ for _ in ()).throw(RuntimeError("boom")))]))
        ex.execute(_intent(), actual_price=4380)
        entries = ex.audit.entries()
        assert any("COMPENSATE" in e["action"] for e in entries)


class TestIdempotencyStateMachine:
    def test_reserve_commit_finalize(self, tmp_path):
        store = IdempotencyStore(tmp_path)
        store.reserve("k1", action="execute_order", target_key="c1")
        assert store.status("k1") == IdempotencyStatus.RESERVED
        store.mark_committed("k1")
        assert store.status("k1") == IdempotencyStatus.COMMITTED
        store.finalize("k1", {"status": "EXECUTED"})
        assert store.status("k1") == IdempotencyStatus.FINALIZED

    def test_duplicate_finalized_rejected(self, tmp_path):
        store = IdempotencyStore(tmp_path)
        store.finalize("k1", {"status": "EXECUTED"})
        from universal_agent.actions import DuplicateRequest
        with pytest.raises(DuplicateRequest):
            store.reserve("k1", action="a", target_key="t")

    def test_commit_crash_reconciliation(self, tmp_path):
        """P0.5 核心：commit 后崩溃 → UNKNOWN → reconcile 查询平台真实状态。"""
        store = IdempotencyStore(tmp_path)
        store.reserve("k1", action="execute_order", target_key="c1")
        store.mark_committed("k1")
        store.mark_unknown("k1")  # 模拟崩溃：commit 后 finalize 前
        assert store.status("k1") == IdempotencyStatus.UNKNOWN
        assert "k1" in store.unresolved()

        # reconcile：平台确认订单已生成 → 定稿 EXECUTED（不重试，防双订单）
        store.reconcile("k1", lambda key: {"confirmed": True, "platform_order": "P123"})
        assert store.status("k1") == IdempotencyStatus.FINALIZED
        assert store.get("k1")["result"]["platform_order"] == "P123"

    def test_reconcile_not_confirmed_retryable(self, tmp_path):
        store = IdempotencyStore(tmp_path)
        store.reserve("k1", action="a", target_key="t")
        store.mark_unknown("k1")
        store.reconcile("k1", lambda key: {"confirmed": False})
        assert store.status("k1") == IdempotencyStatus.FAILED  # 平台无订单 → 可安全重试
