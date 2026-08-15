"""P3 — MemoryDomains 类型化子域访问器测试。"""
from __future__ import annotations

from pathlib import Path

import pytest

from universal_agent.core.contracts import Scope
from universal_agent.memory.domains import MemoryDomains
from universal_agent.memory.sqlite_store import SqliteMemoryStore
from universal_agent.persistence import Database


@pytest.fixture()
def dom(tmp_path: Path) -> MemoryDomains:
    db = Database(tmp_path / "ua.db")
    return MemoryDomains(SqliteMemoryStore(db))


def test_intent_roundtrip(dom) -> None:
    dom.set_intent("flight_zqn", {"origin": "HGH"}, scope=Scope.TASK, task_id="t1")
    got = dom.get_intent("flight_zqn", scope=Scope.TASK, task_id="t1")
    assert got is not None and got.kind == "intent"


def test_preference_roundtrip(dom) -> None:
    dom.set_preference("max_stops", 2, domain="flight", user_id="u1")
    got = dom.get_preference("max_stops", domain="flight", user_id="u1")
    assert got is not None and got.value == 2


def test_decision_roundtrip(dom) -> None:
    dom.set_decision("buy", {"price": 3659}, task_id="t1", source="engine")
    got = dom.get_decision("buy", task_id="t1")
    assert got is not None and got.source == "engine"


def test_observation_roundtrip(dom) -> None:
    dom.set_observation("price", 3659, domain="flight")
    got = dom.get_observation("price", domain="flight")
    assert got is not None and got.value == 3659


def test_answer_roundtrip(dom) -> None:
    dom.set_answer("luggage", {"checked": 1}, task_id="t1", user_id="u1")
    got = dom.get_answer("luggage", task_id="t1", user_id="u1")
    assert got is not None and got.source == "user_confirmed"


def test_task_state_roundtrip(dom) -> None:
    dom.set_task_state("phase", "scanning", task_id="t1")
    got = dom.get_task_state("phase", task_id="t1")
    assert got is not None and got.value == "scanning"


def test_policy_roundtrip(dom) -> None:
    dom.set_policy("max_payment", 5000)
    got = dom.get_policy("max_payment")
    assert got is not None and got.value == 5000


def test_execution_history_roundtrip(dom) -> None:
    dom.set_execution("last", {"run_id": "r1"}, task_id="t1")
    got = dom.get_execution("last", task_id="t1")
    assert got is not None and got.kind == "execution_history"


def test_query_kind_filter(dom) -> None:
    dom.set_preference("a", 1, domain="flight")
    dom.set_observation("b", 2, domain="flight")
    prefs = dom.query(type("Q", (), {"scope": Scope.DOMAIN, "domain": "flight",
                                     "kind": "preference", "task_id": None,
                                     "key": None, "limit": 50})())
    assert len(prefs) == 1 and prefs[0].kind == "preference"
