"""P0.9-6 回归测试：Approval Snapshot 完整性检查。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from universal_agent.actions import (
    IdempotencyStore,
    KillSwitch,
    PolicyEngine,
    TransactionExecutor,
)
from universal_agent.core.contracts import ActionIntent, ActionLevel, Reversibility
from universal_agent.observability.audit import AuditLog


def _intent(**kw) -> ActionIntent:
    defaults = dict(
        intent_id="x", action="execute_order", target_key="c1",
        idempotency_key="idem-x", level=ActionLevel.L4_EXECUTE,
        reversibility=Reversibility.FULL, approved_price_cny=4380.0,
        approved_offer_id="offer-1", approved_quote_id="quote-1",
        approved_at=datetime.now(timezone.utc),
        approval_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    defaults.update(kw)
    return ActionIntent(**defaults)


def _tx(tmp_path) -> TransactionExecutor:
    return TransactionExecutor(
        killswitch=KillSwitch(tmp_path / "ks.json"),
        policy=PolicyEngine(default={"default_deny": False, "rules": [
            {"action": "execute_order", "level": "L4_EXECUTE",
             "requires_approval": False}]}),
        idempotency=IdempotencyStore(tmp_path / "idem"),
        audit=AuditLog(tmp_path / "audit"),
    )


class TestApprovalSnapshot:
    def test_expired_approval_blocks(self, tmp_path):
        ex = _tx(tmp_path)
        intent = _intent(approval_expires_at=datetime.now(timezone.utc) - timedelta(minutes=1))
        out = ex.execute(intent, actual_price=4380)
        assert out.status == "REAPPROVAL_REQUIRED"
        assert "expired" in out.detail["reason"]

    def test_different_offer_requires_reapproval(self, tmp_path):
        ex = _tx(tmp_path)
        intent = _intent(params={"actual_offer_id": "offer-NEW"})
        out = ex.execute(intent, actual_price=4380)
        assert out.status == "REAPPROVAL_REQUIRED"
        assert "offer changed" in out.detail["reason"]

    def test_different_quote_requires_reapproval(self, tmp_path):
        ex = _tx(tmp_path)
        intent = _intent(params={"actual_quote_id": "quote-NEW"})
        out = ex.execute(intent, actual_price=4380)
        assert out.status == "REAPPROVAL_REQUIRED"
        assert "quote changed" in out.detail["reason"]

    def test_baggage_change_requires_reapproval(self, tmp_path):
        ex = _tx(tmp_path)
        intent = _intent(params={"approved_baggage": "2x23kg", "baggage": "1x23kg"})
        out = ex.execute(intent, actual_price=4380)
        assert out.status == "REAPPROVAL_REQUIRED"
        assert "baggage" in out.detail["reason"]

    def test_room_change_requires_reapproval(self, tmp_path):
        ex = _tx(tmp_path)
        intent = _intent(params={"approved_room": "deluxe", "room": "standard"})
        out = ex.execute(intent, actual_price=4380)
        assert out.status == "REAPPROVAL_REQUIRED"
        assert "room" in out.detail["reason"]

    def test_passenger_change_requires_reapproval(self, tmp_path):
        ex = _tx(tmp_path)
        intent = _intent(params={"approved_passenger": "Alice", "passenger": "Bob"})
        out = ex.execute(intent, actual_price=4380)
        assert out.status == "REAPPROVAL_REQUIRED"
        assert "passenger" in out.detail["reason"]

    def test_valid_snapshot_executes(self, tmp_path):
        ex = _tx(tmp_path)
        ex.set_executor(lambda i: ({"ok": True}, []))
        intent = _intent(params={})  # 无变化
        out = ex.execute(intent, actual_price=4380)
        assert out.status == "EXECUTED"

    def test_no_expiry_does_not_block(self, tmp_path):
        ex = _tx(tmp_path)
        ex.set_executor(lambda i: ({"ok": True}, []))
        intent = _intent(approval_expires_at=None)
        out = ex.execute(intent, actual_price=4380)
        assert out.status == "EXECUTED"
