"""P3 — Memory Completion：8 子域类型化 API + user_id/profile_id/confidence。

验收：
1. MemoryRecord 增加 user_id/profile_id/confidence 字段
2. 8 子域类型化访问器：intent/preferences/decisions/answers/task_state/
   policy/execution_history/observations
3. expired 自动过滤（子域级）
4. 全部持久化到 SQLite
"""
from __future__ import annotations

from pathlib import Path

import pytest

from universal_agent.core.contracts import Scope
from universal_agent.memory.sqlite_store import SqliteMemoryStore
from universal_agent.persistence import Database


@pytest.fixture()
def store(tmp_path: Path):
    db = Database(tmp_path / "ua.db")
    return SqliteMemoryStore(db), db


def test_memory_record_new_fields(store) -> None:
    """user_id / profile_id / confidence 字段存在并可存取。"""
    ms, _ = store
    rec = ms.put(Scope.GLOBAL, "pref", {"weight": 0.8},
                 user_id="u1", profile_id="p1", confidence=0.95)
    got = ms.get(Scope.GLOBAL, "pref", user_id="u1")
    assert got is not None
    assert got.user_id == "u1"
    assert got.profile_id == "p1"
    assert got.confidence == 0.95


def test_intent_memory_domain(store) -> None:
    """Intent memory：记录用户表达的目标。"""
    ms, _ = store
    ms.put(Scope.DOMAIN, "intent:flight_to_zqn", {"origin": "HGH", "dest": "ZQN"},
           domain="flight", user_id="u1", kind="intent")
    got = ms.get(Scope.DOMAIN, "intent:flight_to_zqn", domain="flight", user_id="u1")
    assert got is not None and got.kind == "intent"


def test_preference_memory(store) -> None:
    ms, _ = store
    ms.put(Scope.DOMAIN, "pref:max_stops", {"value": 2}, domain="flight",
           user_id="u1", kind="preference")
    got = ms.get(Scope.DOMAIN, "pref:max_stops", domain="flight", user_id="u1")
    assert got is not None and got.kind == "preference"


def test_decision_memory(store) -> None:
    """Decision memory：版本化 + 可解释。"""
    ms, _ = store
    ms.put(Scope.TASK, "decision:buy", {"price": 3659, "reason": "historic low"},
           task_id="t1", kind="decision", source="opportunity_engine")
    got = ms.get(Scope.TASK, "decision:buy", task_id="t1")
    assert got is not None
    assert got.source == "opportunity_engine"
    assert got.value["price"] == 3659


def test_answer_memory_reuse(store) -> None:
    """Answer memory：复用用户确认过的答案。"""
    ms, _ = store
    ms.put(Scope.TASK, "answer:luggage", {"checked": 1}, task_id="t1",
           kind="answer", source="user_confirmed")
    got = ms.get(Scope.TASK, "answer:luggage", task_id="t1")
    assert got is not None and got.source == "user_confirmed"


def test_task_state_memory(store) -> None:
    ms, _ = store
    ms.put(Scope.TASK, "state:phase", {"phase": "scanning"}, task_id="t1", kind="task_state")
    got = ms.get(Scope.TASK, "state:phase", task_id="t1")
    assert got is not None and got.kind == "task_state"


def test_policy_memory(store) -> None:
    ms, _ = store
    ms.put(Scope.GLOBAL, "policy:max_payment", {"amount": 5000}, kind="policy")
    got = ms.get(Scope.GLOBAL, "policy:max_payment")
    assert got is not None and got.kind == "policy"


def test_execution_history_memory(store) -> None:
    ms, _ = store
    ms.put(Scope.TASK, "exec:last_run", {"run_id": "run-1", "ok": True},
           task_id="t1", kind="execution_history")
    got = ms.get(Scope.TASK, "exec:last_run", task_id="t1")
    assert got is not None and got.kind == "execution_history"


def test_observation_memory(store) -> None:
    """Observation memory：观察记录。"""
    ms, _ = store
    ms.put(Scope.DOMAIN, "obs:price", {"price": 3659, "ts": "2026-08-14"},
           domain="flight", kind="observation")
    got = ms.get(Scope.DOMAIN, "obs:price", domain="flight")
    assert got is not None and got.kind == "observation"


def test_expired_filtered_across_subdomains(store) -> None:
    """expired 记录在 get/query 时自动过滤。"""
    from datetime import datetime, timedelta, timezone
    ms, _ = store
    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    ms.put(Scope.GLOBAL, "stale", {"v": 1}, kind="fact", expires_at=past)
    assert ms.get(Scope.GLOBAL, "stale") is None


def test_query_by_kind_and_scope(store) -> None:
    """query 支持按 kind/scope/domain 过滤（子域检索）。"""
    from universal_agent.core.contracts import MemoryQuery
    ms, _ = store
    ms.put(Scope.DOMAIN, "pref:a", {"x": 1}, domain="flight", kind="preference")
    ms.put(Scope.DOMAIN, "fact:b", {"y": 2}, domain="flight", kind="fact")
    prefs = ms.query(MemoryQuery(scope=Scope.DOMAIN, kind="preference"))
    assert len(prefs) == 1 and prefs[0].kind == "preference"
