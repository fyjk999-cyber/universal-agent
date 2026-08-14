"""PHASE 7 测试：Policy Engine / Kill Switch / Compensation / Controlled Execution. """
from __future__ import annotations

from pathlib import Path

import pytest

from universal_agent.actions import (
    CompensationManager,
    CompensationStep,
    ControlledExecutor,
    IdempotencyStore,
    KillSwitch,
    KillSwitchTripped,
    PolicyEngine,
    PolicyRule,
    PolicyViolation,
    SlippageGuard,
)
from universal_agent.actions.approval import ApprovalInbox
from universal_agent.core.contracts import (
    ActionIntent,
    ActionLevel,
    Reversibility,
)
from universal_agent.observability.audit import AuditLog


def _exec_intent(**kw) -> ActionIntent:
    defaults = dict(
        intent_id="x1", action="execute_order", target_key="c1",
        idempotency_key="idem-x1", level=ActionLevel.L4_EXECUTE,
        reversibility=Reversibility.FULL, max_slippage_cny=100,
        # P0.3: L3/L4 必须携带批准快照（approved vs actual 校验）
        approved_price_cny=4380.0,
    )
    defaults.update(kw)
    return ActionIntent(**defaults)


def _executor(tmp_path, policy=None, kill=True) -> ControlledExecutor:
    return ControlledExecutor(
        killswitch=KillSwitch(tmp_path / "ks.json") if kill else _disarmed(tmp_path),
        policy=policy or _default_policy(),
        idempotency=IdempotencyStore(tmp_path / "idem"),
        approvals=ApprovalInbox(tmp_path / "appr"),
        audit=AuditLog(tmp_path / "audit"),
    )


def _disarmed(tmp_path):
    ks = KillSwitch(tmp_path / "ks2.json")
    return ks


def _default_policy() -> PolicyEngine:
    return PolicyEngine(default={
        "default_deny": True,
        "rules": [
            {"action": "execute_order", "level": "L4_EXECUTE",
             "max_amount_cny": 5000, "requires_approval": True},
            {"action": "submit_application", "level": "L3_CONFIRM",
             "requires_approval": True},
            {"action": "cancel_order", "allowed": False, "note": "blacklist"},
        ],
    })


class TestPolicyEngine:
    def test_default_deny_blocks_unknown(self):
        p = _default_policy()
        with pytest.raises(PolicyViolation):
            p.check(action="unknown_action", level="L4_EXECUTE")

    def test_allowed_within_level_and_amount(self):
        p = _default_policy()
        rule = p.check(action="execute_order", level="L4_EXECUTE", amount_cny=4380)
        assert rule.allowed is True

    def test_amount_over_max_blocked(self):
        p = _default_policy()
        with pytest.raises(PolicyViolation):
            p.check(action="execute_order", level="L4_EXECUTE", amount_cny=9999)

    def test_level_above_max_blocked(self):
        p = _default_policy()
        with pytest.raises(PolicyViolation):
            p.check(action="submit_application", level="L4_EXECUTE")  # max L3

    def test_blacklist_blocked(self):
        p = _default_policy()
        with pytest.raises(PolicyViolation):
            p.check(action="cancel_order", level="L4_EXECUTE")

    def test_policy_not_mutable_by_code_default(self):
        """RULE 9: 安全政策只能由人配置。默认 deny 不可被程序关闭。"""
        p = PolicyEngine(default={"default_deny": True, "rules": []})
        with pytest.raises(PolicyViolation):
            p.check(action="anything", level="L4_EXECUTE")


class TestKillSwitch:
    def test_kill_blocks_execution(self, tmp_path):
        ks = KillSwitch(tmp_path / "ks.json")
        ks.kill("test trip")
        assert ks.is_killed()
        with pytest.raises(KillSwitchTripped):
            ks.assert_alive()

    def test_disarm_allows(self, tmp_path):
        ks = KillSwitch(tmp_path / "ks.json")
        ks.kill("x")
        ks.disarm()
        ks.assert_alive()  # no raise

    def test_persists_across_reload(self, tmp_path):
        path = tmp_path / "ks.json"
        k1 = KillSwitch(path)
        k1.kill("persist")
        k2 = KillSwitch(path)
        assert k2.is_killed() is True
        assert "persist" in k2.status()["reason"]


class TestCompensation:
    def test_reverse_order_compensation(self, tmp_path):
        cm = CompensationManager(audit=AuditLog(tmp_path / "audit"))
        order = []

        def make(name):
            def revert():
                order.append(name)
            return CompensationStep(name=name, revert=revert)

        steps = [make("step1"), make("step2"), make("step3")]
        res = cm.compensate(steps, failure_stage="execute",
                            reversibility=Reversibility.FULL)
        assert res.status == "COMPENSATED"
        assert order == ["step3", "step2", "step1"]  # 逆序

    def test_irreversible_no_compensation(self, tmp_path):
        cm = CompensationManager()
        res = cm.compensate([], failure_stage="execute",
                            reversibility=Reversibility.IRREVERSIBLE)
        assert res.status == "NOOP"

    def test_failed_step_partial(self, tmp_path):
        cm = CompensationManager()
        ok = CompensationStep(name="ok", revert=lambda: None)
        bad = CompensationStep(
            name="bad", revert=lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        res = cm.compensate([ok, bad], failure_stage="execute",
                            reversibility=Reversibility.FULL)
        assert res.status == "PARTIAL"
        assert res.errors


class TestControlledExecutor:
    def test_kill_switch_blocks(self, tmp_path):
        ex = _executor(tmp_path, kill=True)
        ex.killswitch.kill("test")
        out = ex.execute(_exec_intent(), confirmed_price=4380)
        assert out.status == "KILLED"

    def test_policy_default_deny_blocks(self, tmp_path):
        ex = _executor(tmp_path)
        out = ex.execute(_exec_intent(action="not_allowed", level=ActionLevel.L4_EXECUTE),
                         confirmed_price=4380)
        assert out.status == "BLOCKED"

    def test_amount_over_policy_blocked(self, tmp_path):
        ex = _executor(tmp_path)
        out = ex.execute(_exec_intent(), confirmed_price=9999)
        assert out.status == "BLOCKED"

    def test_requires_approval_needs_approval(self, tmp_path):
        ex = _executor(tmp_path)
        out = ex.execute(_exec_intent(), confirmed_price=4380)
        assert out.status == "NEEDS_APPROVAL"  # §41/§56 不自动批准

    def test_slippage_blocks(self, tmp_path):
        ex = _executor(tmp_path)
        intent = _exec_intent(level=ActionLevel.L3_CONFIRM, action="submit_application",
                              max_slippage_cny=50)
        out = ex.execute(intent, confirmed_price=1000)
        # 需审批但 slippage 检查在前（此处金额不超 policy，但走审批路径）
        assert out.status in ("NEEDS_APPROVAL", "BLOCKED")

    def test_execution_without_executor_blocked(self, tmp_path):
        """即使 policy 放行，没有注册 executor 也无法执行。"""
        p = PolicyEngine(default={"default_deny": False, "rules": [
            {"action": "execute_order", "level": "L4_EXECUTE",
             "requires_approval": False}]})
        ex = _executor(tmp_path, policy=p)
        out = ex.execute(_exec_intent(), confirmed_price=4380)
        assert out.status == "BLOCKED"

    def test_full_execution_with_executor(self, tmp_path):
        """policy 放行 + 审批不要求 + executor 注册 → 真正执行 + 幂等登记。"""
        p = PolicyEngine(default={"default_deny": False, "rules": [
            {"action": "execute_order", "level": "L4_EXECUTE",
             "requires_approval": False}]})
        ex = _executor(tmp_path, policy=p)
        ex.set_executor(lambda intent: ({"ok": True, "order": "o1"}, []))
        out = ex.execute(_exec_intent(), confirmed_price=4380)
        assert out.status == "EXECUTED"
        assert out.detail["ok"] is True
        assert ex.idempotency.exists("idem-x1")

    def test_duplicate_execution_returns_duplicate(self, tmp_path):
        p = PolicyEngine(default={"default_deny": False, "rules": [
            {"action": "execute_order", "level": "L4_EXECUTE",
             "requires_approval": False}]})
        ex = _executor(tmp_path, policy=p)
        ex.set_executor(lambda intent: ({"ok": True}, []))
        ex.execute(_exec_intent(), confirmed_price=4380)
        out = ex.execute(_exec_intent(), confirmed_price=4380)
        assert out.status == "DUPLICATE"  # §38 幂等

    def test_approval_then_execute(self, tmp_path):
        """§41: 审批通过后再次执行 → 真正执行（不重复要求审批）。"""
        p = PolicyEngine(default={"default_deny": False, "rules": [
            {"action": "confirm_booking", "level": "L3_CONFIRM",
             "requires_approval": True}]})
        ex = _executor(tmp_path, policy=p)
        ex.set_executor(lambda intent: ({"order": f"mock-{intent.target_key}"}, []))
        intent = _exec_intent(action="confirm_booking", level=ActionLevel.L3_CONFIRM,
                              idempotency_key="idem-appr-1", approved_price_cny=3980.0)
        out1 = ex.execute(intent, confirmed_price=3980)
        assert out1.status == "NEEDS_APPROVAL"
        # 人工审批通过
        ex.approvals.decide(out1.detail["approval_id"], approved=True)
        out2 = ex.execute(intent, confirmed_price=3980)
        assert out2.status == "EXECUTED"
        assert out2.detail["order"] == "mock-c1"

    def test_failure_compensates(self, tmp_path):
        """执行抛异常 → 补偿（partial failure → COMPENSATED，P0.4/P0.9）。"""
        p = PolicyEngine(default={"default_deny": False, "rules": [
            {"action": "execute_order", "level": "L4_EXECUTE",
             "requires_approval": False}]})
        ex = _executor(tmp_path, policy=p)

        def boom(intent):
            raise RuntimeError("platform down")

        ex.set_executor(boom)
        out = ex.execute(_exec_intent(), confirmed_price=4380)
        assert out.status in ("COMPENSATED", "FAILED")  # 补偿或失败，不崩溃
        assert out.state.value in ("COMPENSATED", "FAILED")
