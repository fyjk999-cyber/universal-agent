"""Memory Store tests (§16, §17)."""
from __future__ import annotations

from universal_agent.core.contracts import MemoryQuery, Scope
from universal_agent.memory import MemoryStore


class TestMemoryStore:
    def test_upsert_and_version(self, tmp_path):
        store = MemoryStore(tmp_path)
        r1 = store.put(Scope.GLOBAL, "avoid_self_transfer", True, domain="flight")
        assert r1.version == 1
        r2 = store.put(Scope.GLOBAL, "avoid_self_transfer", False, domain="flight")
        assert r2.version == 2
        got = store.get(Scope.GLOBAL, "avoid_self_transfer", domain="flight")
        assert got is not None and got.value is False

    def test_scope_isolation(self, tmp_path):
        store = MemoryStore(tmp_path)
        store.put(Scope.GLOBAL, "k", 1, domain="flight")
        store.put(Scope.TASK, "k", 2, domain="flight", task_id="t1")
        assert store.get(Scope.TASK, "k", domain="flight", task_id="t1").value == 2
        assert store.get(Scope.GLOBAL, "k", domain="flight").value == 1

    def test_query_filters(self, tmp_path):
        store = MemoryStore(tmp_path)
        store.put(Scope.TASK, "a", 1, task_id="t1", kind="preference")
        store.put(Scope.TASK, "b", 2, task_id="t1", kind="fact")
        store.put(Scope.TASK, "c", 3, task_id="t2", kind="preference")
        q = MemoryQuery(scope=Scope.TASK, task_id="t1", kind="preference")
        results = store.query(q)
        assert [r.key for r in results] == ["a"]

    def test_persistence_across_reload(self, tmp_path):
        store = MemoryStore(tmp_path)
        store.put(Scope.GLOBAL, "k", {"x": 1}, domain="flight")
        store2 = MemoryStore(tmp_path)
        got = store2.get(Scope.GLOBAL, "k", domain="flight")
        assert got is not None and got.value == {"x": 1}
