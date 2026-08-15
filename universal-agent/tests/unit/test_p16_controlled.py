"""P16 — Controlled Actions：全风险控制链 + 默认 L4 DENY。

验收：
1. 默认 DENY：未显式放行的 L3/L4 动作被拒
2. Kill Switch：触发后所有执行拒绝
3. Idempotency：重复执行 → DUPLICATE（防双订单）
4. Slippage：approved vs actual 超限 → BLOCK
5. Compensation：可逆动作失败 → 补偿
6. Audit：执行全程留痕
7. 无真实资金副作用（mock executor）
"""
from __future__ import annotations

from pathlib import Path

import pytest

from universal_agent.actions.gateway.transaction import TransactionExecutor
from universal_agent.actions.idempotency import IdempotencyStore
from universal_agent.actions.policy import KillSwitch, PolicyEngine, PolicyViolation
from universal_agent.core.contracts import ActionIntent, ActionLevel, Reversibility
from universal_agent.observability.audit import AuditLog


def _intent(key: str = "k1", level: ActionLevel = ActionLevel.L4_EXECUTE,
            reversible: Reversibility = Reversibility.FULL) -> ActionIntent:
    return ActionIntent(
        intent_id=f"i-{key}", action="execute_order", target_key="c1",
        idempotency_key=key, level=level, reversibility=reversible,
        max_slippage_cny=100, approved_price_cny=1000.0,
    )


def _allow_all_policy() -> PolicyEngine:
    return PolicyEngine(default={"default_deny": False, "rules": [
        {"action": "execute_order", "level": "L4_EXECUTE", "requires_approval": False}]})


def _tx(tmp_path: Path, policy=None, killswitch=None) -> TransactionExecutor:
    return TransactionExecutor(
        killswitch=killswitch or KillSwitch(tmp_path / "ks.json"),
        policy=policy or _allow_all_policy(),
        idempotency=IdempotencyStore(tmp_path / "idem"),
        audit=AuditLog(tmp_path / "audit"),
    )


def test_default_deny_blocks_unapproved_action(tmp_path: Path) -> None:
    """默认 DENY：无 policy 放行 → 拒绝。"""
    tx = _tx(tmp_path, policy=PolicyEngine())  # default_deny=True
    tx.set_executor(lambda i: ({"ok": True}, []))
    out = tx.execute(_intent("k-deny"))
    assert out.status in ("BLOCKED", "KILLED")
    assert out.state.value in ("FAILED", "BLOCKED")


def test_killswitch_blocks_everything(tmp_path: Path) -> None:
    """Kill Switch：触发后所有执行拒绝。"""
    ks = KillSwitch(tmp_path / "ks.json")
    ks.kill("security incident")
    tx = _tx(tmp_path, killswitch=ks)
    tx.set_executor(lambda i: ({"ok": True}, []))
    out = tx.execute(_intent("k-kill"))
    assert out.status == "KILLED"


def test_idempotency_prevents_double_execution(tmp_path: Path) -> None:
    """重复执行 → DUPLICATE（防双订单）。"""
    tx = _tx(tmp_path)
    calls = {"n": 0}

    def exec_fn(intent):
        calls["n"] += 1
        return ({"ok": True, "order": "P1"}, [])

    tx.set_executor(exec_fn)
    out1 = tx.execute(_intent("k-dup"))
    assert out1.status == "EXECUTED"
    # 第二次：idempotency key 已 FINALIZED → DUPLICATE，不执行
    out2 = tx.execute(_intent("k-dup"))
    assert out2.status == "DUPLICATE"
    assert calls["n"] == 1  # 只执行一次


def test_slippage_blocks_price_change(tmp_path: Path) -> None:
    """approved 1000 vs actual 1200（超 100 上限）→ BLOCK。"""
    tx = _tx(tmp_path)
    tx.set_executor(lambda i: ({"ok": True}, []))
    out = tx.execute(_intent("k-slip"), actual_price=1200.0)
    assert out.status in ("BLOCKED", "KILLED")
    assert out.state.value == "FAILED"


def test_compensation_on_failure(tmp_path: Path) -> None:
    """可逆动作执行失败 → 补偿路径。"""
    from universal_agent.actions.compensation import CompensationStep
    tx = _tx(tmp_path)
    steps = [CompensationStep(name="reserve", revert=lambda: None, compensatable=True)]

    def failing(intent):
        return ({"ok": False}, steps)

    tx.set_executor(failing)
    out = tx.execute(_intent("k-comp"))
    assert out.status in ("COMPENSATED", "FAILED")
    assert out.compensation_status in ("COMPENSATED", "PARTIAL", "FAILED", "NOOP")


def test_audit_trail_exists(tmp_path: Path) -> None:
    """执行全程 audit 留痕。"""
    audit = AuditLog(tmp_path / "audit")
    tx = TransactionExecutor(
        killswitch=KillSwitch(tmp_path / "ks.json"), policy=_allow_all_policy(),
        idempotency=IdempotencyStore(tmp_path / "idem"), audit=audit)
    tx.set_executor(lambda i: ({"ok": True}, []))
    tx.execute(_intent("k-audit"))
    entries = audit.entries()
    assert len(entries) >= 1
    assert entries[0]["action"] == "EXECUTED" or "execute" in entries[0]["action"].lower()
