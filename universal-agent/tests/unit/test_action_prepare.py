"""PHASE 6 测试：风险控制骨架（§37-§41, §50）+ PREPARE 管线（§65）。"""
from __future__ import annotations

from pathlib import Path

import pytest

from universal_agent.actions import (
    ActionPreparer,
    ApprovalInbox,
    DuplicateRequest,
    IdempotencyStore,
    SlippageGuard,
)
from universal_agent.core.contracts import (
    ActionIntent,
    ActionLevel,
    Reversibility,
)
from universal_agent.observability.audit import AuditLog
from universal_agent.registry import CapabilityDenied


def _prepare_intent(**kw) -> ActionIntent:
    defaults = dict(
        intent_id="i1", action="prepare_order", target_key="c1",
        idempotency_key="idem-1", level=ActionLevel.L2_PREPARE,
        reversibility=Reversibility.TIME_LIMITED,
        max_slippage_cny=100, max_slippage_percent=2.0,
    )
    defaults.update(kw)
    return ActionIntent(**defaults)


def _preparer(tmp_path) -> ActionPreparer:
    return ActionPreparer(
        idempotency=IdempotencyStore(tmp_path / "idem"),
        approvals=ApprovalInbox(tmp_path / "approvals"),
        audit=AuditLog(tmp_path / "audit"),
    )


class TestIdempotency:
    def test_register_and_duplicate(self, tmp_path):
        store = IdempotencyStore(tmp_path)
        store.register("k1", action="prepare_order", target_key="c1",
                       result={"status": "PREPARED"})
        assert store.exists("k1")
        # 同 key 同结果 → 返回已有
        rec = store.register("k1", action="prepare_order", target_key="c1",
                             result={"status": "PREPARED"})
        assert rec["key"] == "k1"
        # 同 key 不同结果 → DuplicateRequest
        with pytest.raises(DuplicateRequest):
            store.register("k1", action="prepare_order", target_key="c1",
                           result={"status": "EXECUTED"})

    def test_persistence_across_reload(self, tmp_path):
        s1 = IdempotencyStore(tmp_path)
        s1.register("k", action="a", target_key="t", result={"ok": 1})
        s2 = IdempotencyStore(tmp_path)
        assert s2.exists("k")


class TestSlippageGuard:
    def test_within_limit_allowed(self):
        r = SlippageGuard().check(4380, 4400, max_cny=100, max_percent=2.0)
        assert r.allowed is True

    def test_over_cny_aborts(self):
        """§39: 确认 ¥4380 执行变 ¥4750 → ABORT. """
        r = SlippageGuard().check(4380, 4750, max_cny=100, max_percent=2.0)
        assert r.allowed is False
        assert "slippage" in r.reason

    def test_over_percent_aborts(self):
        r = SlippageGuard().check(4380, 4600, max_cny=1000, max_percent=2.0)
        assert r.allowed is False  # 5% > 2%


class TestApprovalInbox:
    def test_request_never_auto_approved(self, tmp_path):
        """§56: 审批请求绝不自动通过。"""
        inbox = ApprovalInbox(tmp_path)
        item = inbox.request(approval_type="purchase", title="buy flight",
                             payload={"price": 4380})
        assert item["status"] == "PENDING"
        assert item["decision"] is None

    def test_decide_approve_reject(self, tmp_path):
        inbox = ApprovalInbox(tmp_path)
        item = inbox.request(approval_type="job_application", title="apply")
        approved = inbox.decide(item["approval_id"], approved=True)
        assert approved["status"] == "APPROVED"
        with pytest.raises(ValueError):
            inbox.decide(item["approval_id"], approved=False)  # 已决定

    def test_pending_list(self, tmp_path):
        inbox = ApprovalInbox(tmp_path)
        inbox.request(approval_type="purchase", title="a")
        inbox.request(approval_type="order", title="b")
        assert len(inbox.pending()) == 2


class TestAuditLog:
    def test_append_only_six_fields(self, tmp_path):
        log = AuditLog(tmp_path)
        entry = log.record(actor="user", action="PREPARE::prepare_order",
                           reason="to confirmation page",
                           based_on={"intent_id": "i1"},
                           approved=None, result={"approval_id": "ap1"})
        assert entry["actor"] == "user"
        for k in ("ts", "actor", "action", "reason", "based_on", "approved", "result"):
            assert k in entry
        entries = log.entries()
        assert len(entries) == 1


class TestActionPreparer:
    def test_prepare_success_creates_approval_and_audit(self, tmp_path):
        prep = _preparer(tmp_path)
        outcome = prep.prepare(_prepare_intent(), confirmed_price=4380)
        assert outcome.status == "PREPARED"
        assert outcome.approval is not None
        assert outcome.approval["status"] == "PENDING"
        assert outcome.audit_ref is not None
        # 幂等已登记
        assert prep.idempotency.exists("idem-1")

    def test_prepare_duplicate_returns_duplicate_status(self, tmp_path):
        prep = _preparer(tmp_path)
        intent = _prepare_intent()
        prep.prepare(intent, confirmed_price=4380)
        outcome = prep.prepare(intent, confirmed_price=4380)
        assert outcome.status == "DUPLICATE"  # §38 防重复

    def test_irreversible_prepare_rejected(self, tmp_path):
        prep = _preparer(tmp_path)
        with pytest.raises(CapabilityDenied):
            prep.prepare(_prepare_intent(reversibility=Reversibility.IRREVERSIBLE))

    def test_prepare_is_not_commit(self, tmp_path):
        """§65: PREPARE 不产生任何外部副作用（无 execute，只建审批）。"""
        prep = _preparer(tmp_path)
        outcome = prep.prepare(_prepare_intent(), confirmed_price=4380)
        # 状态是 PREPARED 而非 EXECUTED；无结果执行记录
        assert outcome.status == "PREPARED"
        assert "EXECUTED" != outcome.status

    def test_l3_confirm_rejected(self, tmp_path):
        prep = _preparer(tmp_path)
        intent = _prepare_intent(level=ActionLevel.L3_CONFIRM)
        with pytest.raises(CapabilityDenied):
            prep.prepare(intent)
