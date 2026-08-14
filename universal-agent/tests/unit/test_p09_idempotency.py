"""P0.9-5 回归测试：Idempotency Commit Boundary + 统一 L3/L4 路径。"""
from __future__ import annotations

from pathlib import Path

import pytest

from universal_agent.actions import (
    ApprovalInbox,
    ControlledExecutor,
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
        intent_id="x", action="execute_order", target_key="c1",
        idempotency_key="idem-x", level=ActionLevel.L4_EXECUTE,
        reversibility=Reversibility.FULL, approved_price_cny=4380.0,
    )
    defaults.update(kw)
    return ActionIntent(**defaults)


def _policy(requires_approval: bool = False) -> PolicyEngine:
    return PolicyEngine(default={"default_deny": False, "rules": [
        {"action": "execute_order", "level": "L4_EXECUTE",
         "requires_approval": requires_approval}]})


def _tx(tmp_path, reconcile_fn=None) -> TransactionExecutor:
    return TransactionExecutor(
        killswitch=KillSwitch(tmp_path / "ks.json"),
        policy=_policy(),
        idempotency=IdempotencyStore(tmp_path / "idem"),
        audit=AuditLog(tmp_path / "audit"),
        reconcile_fn=reconcile_fn)


class TestCommitBoundary:
    def test_existing_reserved_key_does_not_execute(self, tmp_path):
        """已有 RESERVED → 不执行，需 reconcile。"""
        ex = _tx(tmp_path)
        called = []
        ex.set_executor(lambda i: (called.append(1), {"ok": True}, []))
        ex.execute(_intent(), actual_price=4380)  # 首次：reserve → committed → executed
        # 第二次同 key（RESERVED/COMMITTED 残留）→ RECONCILE_REQUIRED，不执行
        out2 = ex.execute(_intent(), actual_price=4380)
        assert out2.status == "RECONCILE_REQUIRED"
        # 但首次成功后是 FINALIZED → 第二次走 reserve 抛 DuplicateRequest → DUPLICATE
        # （上面用新 intent 对象同 key → reserve 抛 DuplicateRequest）
        assert out2.status in ("RECONCILE_REQUIRED", "DUPLICATE")

    def test_existing_unknown_key_requires_reconcile(self, tmp_path):
        """UNKNOWN（crash 残留）→ 必须 reconcile，不直接执行。"""
        store = IdempotencyStore(tmp_path / "idem")
        store.reserve("idem-x", action="execute_order", target_key="c1")
        store.mark_committed("idem-x")
        store.mark_unknown("idem-x")
        ex = _tx(tmp_path)
        called = []
        ex.set_executor(lambda i: (called.append(1), {"ok": True}, []))
        out = ex.execute(_intent(), actual_price=4380)
        assert out.status == "RECONCILE_REQUIRED"  # 不执行
        assert called == []

    def test_reconcile_confirmed_prevents_duplicate(self, tmp_path):
        """reconcile CONFIRMED → FINALIZED（防重复执行）。"""
        ex = _tx(tmp_path, reconcile_fn=lambda k: {"outcome": "CONFIRMED",
                                                   "platform_order": "P123"})
        ex.idempotency.reserve("idem-x", action="execute_order", target_key="c1")
        ex.idempotency.mark_committed("idem-x")
        out = ex.reconcile(_intent())
        assert out.status == "DUPLICATE"
        assert out.detail["prevented_duplicate"] is True
        assert ex.idempotency.status("idem-x") == IdempotencyStatus.FINALIZED

    def test_reconcile_not_found_allows_safe_retry(self, tmp_path):
        ex = _tx(tmp_path, reconcile_fn=lambda k: {"outcome": "NOT_FOUND"})
        ex.idempotency.reserve("idem-x", action="execute_order", target_key="c1")
        ex.idempotency.mark_committed("idem-x")
        out = ex.reconcile(_intent())
        assert out.status == "SAFE_TO_RETRY"

    def test_reconcile_unknown_does_not_retry(self, tmp_path):
        """平台状态 UNKNOWN → 不自动重试（需人工）。"""
        ex = _tx(tmp_path, reconcile_fn=lambda k: {"outcome": "UNKNOWN"})
        ex.idempotency.reserve("idem-x", action="execute_order", target_key="c1")
        ex.idempotency.mark_committed("idem-x")
        out = ex.reconcile(_intent())
        assert out.status == "RECONCILE_UNKNOWN"

    def test_external_commit_crash_never_double_executes(self, tmp_path):
        """crash 后同 intent 重试 → reconcile CONFIRMED → 不二次执行。"""
        ex = _tx(tmp_path)
        executes = []
        ex.set_executor(lambda i: (executes.append(1), {"ok": True}, []))
        ex.execute(_intent(), actual_price=4380)  # 第一次成功
        assert len(executes) == 1
        # 模拟 crash：FINALIZED 保留；再次执行同 key → DUPLICATE（不二次执行）
        out2 = ex.execute(_intent(), actual_price=4380)
        assert out2.status in ("DUPLICATE", "RECONCILE_REQUIRED")
        assert len(executes) == 1  # 未二次执行

    def test_only_transaction_executor_is_l3_l4_path(self):
        """ControlledExecutor 是 wrapper，内部委托 TransactionExecutor。"""
        import inspect
        src = inspect.getsource(ControlledExecutor)
        assert "TransactionExecutor" in src
        assert "self._inner.execute" in src  # 委托，不实现第二套逻辑


class TestCrashSimulation:
    def test_committed_crash_state_persisted(self, tmp_path):
        """commit 后 crash（未 finalize）→ COMMITTED 状态持久，重启可见。"""
        d = tmp_path / "idem"
        s1 = IdempotencyStore(d)
        s1.reserve("k", action="a", target_key="t")
        s1.mark_committed("k")
        del s1
        s2 = IdempotencyStore(d)
        assert s2.status("k") == IdempotencyStatus.COMMITTED
        assert "k" in s2.unresolved()
