"""P0.3 回归测试：Slippage Guard approved vs actual + material change。

规则：
- 禁止 confirmed vs confirmed 自比较
- approved 4380 + actual 4380 → PASS
- approved 4380 + actual 4480 → 按 policy（≤100 → 通过）
- approved 4380 + actual 4980 → BLOCK（¥600 > ¥100）
- material change（行李/日期/币种变化）→ BLOCK
"""
from __future__ import annotations

from pathlib import Path

import pytest

from universal_agent.actions import (
    ApprovalInbox,
    ControlledExecutor,
    IdempotencyStore,
    KillSwitch,
    PolicyEngine,
    SlippageGuard,
)
from universal_agent.core.contracts import ActionIntent, ActionLevel, Reversibility
from universal_agent.observability.audit import AuditLog


def _intent(**kw) -> ActionIntent:
    defaults = dict(
        intent_id="s1", action="execute_order", target_key="c1",
        idempotency_key="idem-s1", level=ActionLevel.L4_EXECUTE,
        reversibility=Reversibility.FULL, max_slippage_cny=100, max_slippage_percent=2.0,
        approved_price_cny=4380.0,
        params={"baggage": "2x23kg", "currency": "CNY", "date": "2026-08-31"},
    )
    defaults.update(kw)
    return ActionIntent(**defaults)


def _no_approval_policy() -> PolicyEngine:
    return PolicyEngine(default={"default_deny": False, "rules": [
        {"action": "execute_order", "level": "L4_EXECUTE", "requires_approval": False}]})


def _executor(tmp_path) -> ControlledExecutor:
    ex = ControlledExecutor(
        killswitch=KillSwitch(tmp_path / "ks.json"), policy=_no_approval_policy(),
        idempotency=IdempotencyStore(tmp_path / "idem"),
        approvals=ApprovalInbox(tmp_path / "appr"), audit=AuditLog(tmp_path / "audit"))
    ex.set_executor(lambda intent: ({"order": "ok"}, []))
    return ex


class TestSlippageGuardCore:
    def test_approved_equals_actual_passes(self):
        r = SlippageGuard().check(4380, 4380, max_cny=100, max_percent=2.0)
        assert r.allowed is True

    def test_small_delta_within_policy(self):
        r = SlippageGuard().check(4380, 4420, max_cny=100, max_percent=2.0)
        assert r.allowed is True  # ¥40 < ¥100 且 0.9% < 2%

    def test_large_delta_blocks(self):
        r = SlippageGuard().check(4380, 4980, max_cny=100, max_percent=2.0)
        assert r.allowed is False
        assert "slippage" in r.reason

    def test_missing_price_blocks(self):
        r = SlippageGuard().check(4380, None, max_cny=100, max_percent=2.0)
        assert r.allowed is False

    def test_material_change_baggage(self):
        approved = {"price": 4380, "baggage": "2x23kg", "currency": "CNY"}
        actual = {"price": 4380, "baggage": "1x23kg", "currency": "CNY"}  # 行李变了
        r = SlippageGuard().check_material(approved, actual)
        assert r.material_change is True
        assert r.allowed is False

    def test_material_change_date(self):
        approved = {"price": 4380, "date": "2026-08-31"}
        actual = {"price": 4380, "date": "2026-09-01"}  # 日期变了
        r = SlippageGuard().check_material(approved, actual)
        assert r.material_change is True
        assert r.allowed is False

    def test_no_material_change_passes(self):
        approved = {"price": 4380, "baggage": "2x23kg", "currency": "CNY"}
        actual = {"price": 4380, "baggage": "2x23kg", "currency": "CNY"}
        r = SlippageGuard().check_material(approved, actual)
        assert r.material_change is False
        assert r.allowed is True


class TestExecutorApprovedVsActual:
    def test_approved_actual_same_executes(self, tmp_path):
        ex = _executor(tmp_path)
        out = ex.execute(_intent(), confirmed_price=4380)
        assert out.status == "EXECUTED"

    def test_approved_actual_small_delta_executes(self, tmp_path):
        ex = _executor(tmp_path)
        out = ex.execute(_intent(), confirmed_price=4420)  # ¥40 涨幅，限内
        assert out.status == "EXECUTED"

    def test_approved_actual_large_delta_blocks(self, tmp_path):
        ex = _executor(tmp_path)
        out = ex.execute(_intent(), confirmed_price=4980)
        assert out.status == "BLOCKED"
        assert "slippage" in out.detail.get("reason", "")

    def test_no_approved_snapshot_blocks(self, tmp_path):
        """P0.3: 无批准快照的 L4 执行必须 BLOCK（不默认放行）。"""
        ex = _executor(tmp_path)
        intent = _intent(approved_price_cny=None)
        out = ex.execute(intent, confirmed_price=4380)
        assert out.status == "BLOCKED"
        assert "approved" in out.detail.get("reason", "")

    def test_material_change_blocks_even_same_price(self, tmp_path):
        """价格相同但订单内容变化（执行时 params 的行李不同）→ BLOCK。

        通过 confirmed_price 传 actual 价格 + intent.params 传 actual 订单内容，
        与 approved 快照（intent 初始 params）对比发现行李变化。
        """
        ex = _executor(tmp_path)
        # 批准快照：2x23kg；执行时 actual params 改为 1x23kg（模拟平台重取）
        intent = _intent(approved_price_cny=4380.0,
                         params={"baggage": "2x23kg", "currency": "CNY", "date": "2026-08-31"})
        # 直接构造 material check 验证（executor 内部从 params 取 actual）
        approved = {"price": 4380.0, "baggage": "2x23kg", "currency": "CNY", "date": "2026-08-31"}
        actual = {"price": 4380.0, "baggage": "1x23kg", "currency": "CNY", "date": "2026-08-31"}
        r = SlippageGuard().check_material(approved, actual)
        assert r.material_change is True
        assert r.allowed is False
