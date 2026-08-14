"""P0.9-8 集成测试 3：Transaction Crash — reconcile 防二次执行。"""
from __future__ import annotations

from pathlib import Path

import pytest

from universal_agent.actions import (
    IdempotencyStatus,
    IdempotencyStore,
    KillSwitch,
    PolicyEngine,
    TransactionExecutor,
)
from universal_agent.core.contracts import ActionIntent, ActionLevel, Reversibility
from universal_agent.observability.audit import AuditLog


def _intent() -> ActionIntent:
    return ActionIntent(
        intent_id="crash-1", action="execute_order", target_key="c1",
        idempotency_key="idem-crash-1", level=ActionLevel.L4_EXECUTE,
        reversibility=Reversibility.FULL, approved_price_cny=4380.0,
    )


def _policy() -> PolicyEngine:
    return PolicyEngine(default={"default_deny": False, "rules": [
        {"action": "execute_order", "level": "L4_EXECUTE", "requires_approval": False}]})


class TestTransactionCrash:
    def test_crash_before_finalize_requires_reconcile(self, tmp_path):
        """外部副作用已发生但 crash 前未 finalize → 重启后必须 reconcile，不二次执行。"""
        d = tmp_path / "idem"
        # 阶段 1：reserve + 外部副作用模拟 + crash（只到 COMMITTED）
        s1 = IdempotencyStore(d)
        s1.reserve("idem-crash-1", action="execute_order", target_key="c1")
        s1.mark_committed("idem-crash-1")  # 外部副作用已发生，未 finalize 即 crash
        # 记录平台侧副作用（模拟下单成功）
        del s1  # crash

        # 阶段 2：重启
        ex = TransactionExecutor(
            killswitch=KillSwitch(tmp_path / "ks.json"),
            policy=_policy(),
            idempotency=IdempotencyStore(d),
            audit=AuditLog(tmp_path / "audit"),
            reconcile_fn=lambda k: {"outcome": "CONFIRMED", "platform_order": "P999"})
        executes = []
        ex.set_executor(lambda i: (executes.append(1), {"ok": True}, []))

        # 重启后同 intent → 不能直接执行，必须 reconcile
        out = ex.execute(_intent(), actual_price=4380)
        assert out.status == "RECONCILE_REQUIRED"
        assert executes == []  # 未二次执行

        # reconcile：平台 CONFIRMED → FINALIZED，防重复
        rec = ex.reconcile(_intent())
        assert rec.status == "DUPLICATE"
        assert rec.detail["prevented_duplicate"] is True
        assert executes == []  # 始终未二次执行
        assert ex.idempotency.status("idem-crash-1") == IdempotencyStatus.FINALIZED

    def test_crash_not_found_allows_retry(self, tmp_path):
        """平台无副作用（NOT_FOUND）→ 可安全重试。"""
        ex = TransactionExecutor(
            killswitch=KillSwitch(tmp_path / "ks.json"),
            policy=_policy(),
            idempotency=IdempotencyStore(tmp_path / "idem"),
            audit=AuditLog(tmp_path / "audit"),
            reconcile_fn=lambda k: {"outcome": "NOT_FOUND"})
        intent2 = _intent()
        intent2.idempotency_key = "idem-crash-2"
        ex.idempotency.reserve("idem-crash-2", action="execute_order", target_key="c1")
        ex.idempotency.mark_committed("idem-crash-2")
        out = ex.reconcile(intent2)
        assert out.status == "SAFE_TO_RETRY"
