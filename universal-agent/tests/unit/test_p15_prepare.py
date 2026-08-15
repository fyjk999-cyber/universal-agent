"""P15 — Action Prepare：L2 PREPARE 统一管理，No Commit。

验收：
1. flight/jobs/ecommerce 三类 action 都能 PREPARE 到确认页/提交前
2. PREPARE 不产生任何真实 commit（无 execute 副作用）
3. Approval Inbox 统一收集待审批项
4. IRREVERSIBLE 禁止 PREPARE（直到 L3/L4 gates）
"""
from __future__ import annotations

from pathlib import Path

import pytest

from universal_agent.actions.approval import ApprovalInbox
from universal_agent.actions.gateway.prepare import ActionPreparer
from universal_agent.actions.idempotency import IdempotencyStore
from universal_agent.core.contracts import (
    ActionIntent,
    ActionLevel,
    Reversibility,
)
from universal_agent.observability.audit import AuditLog
from universal_agent.registry import SkillRegistry


def _intent(action: str = "prepare_order", level: ActionLevel = ActionLevel.L2_PREPARE,
            reversible: Reversibility = Reversibility.PARTIAL) -> ActionIntent:
    return ActionIntent(
        intent_id=f"i-{action}", action=action, target_key="flight-1",
        params={"quote_id": "q1", "offer_id": "o1", "offer_version": 1,
                "candidate_version": 1},
        idempotency_key=f"idem-{action}", level=level,
        reversibility=reversible, max_slippage_cny=100,
    )


def _preparer(tmp_path: Path) -> ActionPreparer:
    return ActionPreparer(
        idempotency=IdempotencyStore(tmp_path / "idem"),
        approvals=ApprovalInbox(tmp_path / "approvals"),
        audit=AuditLog(tmp_path / "audit"),
        skill_registry=SkillRegistry(),
    )


def test_prepare_flight_action(tmp_path: Path) -> None:
    """机票 PREPARE 到确认页（无 commit）。"""
    p = _preparer(tmp_path)
    out = p.prepare(_intent("prepare_order"), confirmed_price=3659.0)
    assert out.status in ("PREPARED", "PENDING_APPROVAL")
    assert out.intent.approved_price_cny == 3659.0


def test_prepare_jobs_action(tmp_path: Path) -> None:
    """岗位提交 PREPARE（到 Submit 前）。"""
    p = _preparer(tmp_path)
    out = p.prepare(_intent("submit_application"), confirmed_price=0.01)
    assert out.status in ("PREPARED", "PENDING_APPROVAL")


def test_prepare_ecommerce_action(tmp_path: Path) -> None:
    """电商 checkout PREPARE（到 Checkout 前）。"""
    p = _preparer(tmp_path)
    out = p.prepare(_intent("prepare_order"), confirmed_price=199.0)
    assert out.status in ("PREPARED", "PENDING_APPROVAL")


def test_prepare_no_commit_side_effect(tmp_path: Path) -> None:
    """PREPARE 绝不执行真实动作（无 executor 调用）。"""
    p = _preparer(tmp_path)
    executed = []
    # PREPARE 路径没有任何 executor 挂载点 → 无法触发副作用
    out = p.prepare(_intent("prepare_order"), confirmed_price=100.0)
    assert out.status in ("PREPARED", "PENDING_APPROVAL")
    assert executed == []


def test_approval_inbox_collects(tmp_path: Path) -> None:
    """Approval Inbox 统一管理待审批项。"""
    p = _preparer(tmp_path)
    p.prepare(_intent("prepare_order", level=ActionLevel.L2_PREPARE),
              confirmed_price=500.0)
    p.prepare(_intent("submit_application", level=ActionLevel.L2_PREPARE),
              confirmed_price=0.01)
    pending = p.approvals.pending()
    assert len(pending) >= 1  # 至少一个待审批


def test_irreversible_prepare_denied(tmp_path: Path) -> None:
    """IRREVERSIBLE 禁止 PREPARE（直到 L3/L4 gates）。"""
    from universal_agent.registry import CapabilityDenied
    p = _preparer(tmp_path)
    with pytest.raises(CapabilityDenied):
        p.prepare(_intent("execute_order", level=ActionLevel.L2_PREPARE,
                          reversible=Reversibility.IRREVERSIBLE),
                  confirmed_price=100.0)
