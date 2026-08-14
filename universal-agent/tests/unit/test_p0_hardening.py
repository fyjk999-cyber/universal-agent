"""P0.8 测试硬化 — 用户指定的关键行为精确断言。

覆盖：
- test_notification_survives_restart
- 精确断言（禁止 "assert status in (BLOCKED, NEEDS_APPROVAL)" 模糊掩盖）
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from universal_agent.notifications import NotificationDedup

NOW = datetime(2026, 8, 14, 9, 0, tzinfo=timezone.utc)


class TestNotificationPersistent:
    def test_notification_survives_restart(self, tmp_path):
        """P0.8 核心：重启后 dedup 仍记得已提醒（cooldown 状态持久化）。"""
        state = tmp_path / "dedup.json"
        d1 = NotificationDedup(cooldown_minutes=720, state_path=state)
        assert d1.should_notify("t1", "c1", {"price": 4380}, now=NOW) is True
        d1.record("t1", "c1", {"price": 4380}, now=NOW)
        # 模拟重启
        d2 = NotificationDedup(cooldown_minutes=720, state_path=state)
        # 重启后同 material 在 cooldown 内 → 仍抑制（不重复轰炸）
        assert d2.should_notify("t1", "c1", {"price": 4380},
                                now=NOW + timedelta(hours=2)) is False

    def test_cooldown_elapsed_after_restart(self, tmp_path):
        state = tmp_path / "dedup.json"
        d1 = NotificationDedup(cooldown_minutes=60, state_path=state)
        d1.record("t1", "c1", {"price": 4380}, now=NOW)
        d2 = NotificationDedup(cooldown_minutes=60, state_path=state)
        # cooldown 过后 → 允许再次提醒
        assert d2.should_notify("t1", "c1", {"price": 4380},
                                now=NOW + timedelta(hours=2)) is True


class TestPreciseAssertions:
    """§P0.8：禁止模糊断言（BLOCKED/NEEDS_APPROVAL 二选一），必须精确。"""

    def test_large_slippage_precisely_blocked(self, tmp_path):
        """精确断言：¥600 涨幅 → 精确 BLOCKED（不是 NEEDS_APPROVAL）。"""
        from universal_agent.actions import (
            ApprovalInbox,
            IdempotencyStore,
            KillSwitch,
            PolicyEngine,
            SlippageGuard,
        )
        from universal_agent.core.contracts import ActionIntent, ActionLevel, Reversibility
        from universal_agent.observability.audit import AuditLog
        from universal_agent.actions.gateway.execute import ControlledExecutor

        ex = ControlledExecutor(
            killswitch=KillSwitch(tmp_path / "ks.json"),
            policy=PolicyEngine(default={"default_deny": False, "rules": [
                {"action": "execute_order", "level": "L4_EXECUTE",
                 "requires_approval": True}]}),
            idempotency=IdempotencyStore(tmp_path / "idem"),
            approvals=ApprovalInbox(tmp_path / "appr"),
            audit=AuditLog(tmp_path / "audit"),
            slippage=SlippageGuard(),
        )
        intent = ActionIntent(
            intent_id="x", action="execute_order", target_key="c",
            idempotency_key="idem-x", level=ActionLevel.L4_EXECUTE,
            reversibility=Reversibility.FULL, max_slippage_cny=100,
            approved_price_cny=4380.0,
        )
        out = ex.execute(intent, confirmed_price=4980)
        assert out.status == "BLOCKED"  # 精确：滑移超限直接 BLOCK，非 NEEDS_APPROVAL
        assert out.detail["reason"].startswith("slippage")

    def test_success_precisely_executed_not_compensated(self, tmp_path):
        """精确断言：成功 = EXECUTED + compensation NOOP。"""
        from universal_agent.actions import (
            IdempotencyStore,
            KillSwitch,
            PolicyEngine,
            TransactionExecutor,
        )
        from universal_agent.core.contracts import ActionIntent, ActionLevel, Reversibility
        from universal_agent.observability.audit import AuditLog

        ex = TransactionExecutor(
            killswitch=KillSwitch(tmp_path / "ks2.json"),
            policy=PolicyEngine(default={"default_deny": False, "rules": [
                {"action": "execute_order", "level": "L4_EXECUTE",
                 "requires_approval": False}]}),
            idempotency=IdempotencyStore(tmp_path / "idem2"),
            audit=AuditLog(tmp_path / "audit2"),
        )
        ex.set_executor(lambda intent: ({"ok": True}, []))
        intent = ActionIntent(
            intent_id="y", action="execute_order", target_key="c",
            idempotency_key="idem-y", level=ActionLevel.L4_EXECUTE,
            reversibility=Reversibility.FULL, approved_price_cny=4380.0,
        )
        out = ex.execute(intent, actual_price=4380)
        assert out.status == "EXECUTED"
        assert out.compensation_status == "NOOP"  # 成功绝不补偿
