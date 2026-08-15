"""Memory 子域类型化访问器（P3）。

把 8 个 Memory 子域封装为类型化方法，业务代码不再手写 kind 字符串：
  Intent / Preference / Decision / Observation / Answer / TaskState /
  Policy / ExecutionHistory

每个子域 = 特定 kind + 常用参数；底层仍是 SqliteMemoryStore（单一真相）。
"""
from __future__ import annotations

from typing import Any, List, Optional

from ..core.contracts import MemoryQuery, MemoryRecord, Scope
from .sqlite_store import SqliteMemoryStore


class MemoryDomains:
    """类型化 Memory 子域访问器。"""

    def __init__(self, store: SqliteMemoryStore) -> None:
        self._store = store

    # ---- Intent（用户表达的目标）----
    def set_intent(self, key: str, value: Any, *, scope: Scope = Scope.TASK,
                   domain: Optional[str] = None, task_id: Optional[str] = None,
                   user_id: Optional[str] = None, confidence: Optional[float] = None) -> MemoryRecord:
        return self._store.put(scope, f"intent:{key}", value, domain=domain,
                               task_id=task_id, kind="intent", user_id=user_id,
                               confidence=confidence)

    def get_intent(self, key: str, *, scope: Scope = Scope.TASK,
                   domain: Optional[str] = None, task_id: Optional[str] = None,
                   user_id: Optional[str] = None) -> Optional[MemoryRecord]:
        return self._store.get(scope, f"intent:{key}", domain=domain,
                               task_id=task_id, user_id=user_id)

    # ---- Preference（偏好；可被 Preference Learning 改变）----
    def set_preference(self, key: str, value: Any, *, scope: Scope = Scope.DOMAIN,
                       domain: Optional[str] = None, user_id: Optional[str] = None,
                       confidence: Optional[float] = None) -> MemoryRecord:
        return self._store.put(scope, f"pref:{key}", value, domain=domain,
                               kind="preference", user_id=user_id, confidence=confidence)

    def get_preference(self, key: str, *, scope: Scope = Scope.DOMAIN,
                       domain: Optional[str] = None,
                       user_id: Optional[str] = None) -> Optional[MemoryRecord]:
        return self._store.get(scope, f"pref:{key}", domain=domain, user_id=user_id)

    # ---- Decision（版本化、可解释）----
    def set_decision(self, key: str, value: Any, *, task_id: str,
                     source: str = "system", confidence: Optional[float] = None) -> MemoryRecord:
        return self._store.put(Scope.TASK, f"decision:{key}", value, task_id=task_id,
                               kind="decision", source=source, confidence=confidence)

    def get_decision(self, key: str, *, task_id: str) -> Optional[MemoryRecord]:
        return self._store.get(Scope.TASK, f"decision:{key}", task_id=task_id)

    # ---- Observation（观察记录）----
    def set_observation(self, key: str, value: Any, *, domain: Optional[str] = None,
                        task_id: Optional[str] = None,
                        source: str = "scanner") -> MemoryRecord:
        return self._store.put(Scope.DOMAIN, f"obs:{key}", value, domain=domain,
                               task_id=task_id, kind="observation", source=source)

    def get_observation(self, key: str, *, domain: Optional[str] = None,
                        task_id: Optional[str] = None) -> Optional[MemoryRecord]:
        return self._store.get(Scope.DOMAIN, f"obs:{key}", domain=domain, task_id=task_id)

    # ---- Answer（用户确认过的答案，可复用）----
    def set_answer(self, key: str, value: Any, *, task_id: Optional[str] = None,
                   user_id: Optional[str] = None) -> MemoryRecord:
        return self._store.put(Scope.TASK, f"answer:{key}", value, task_id=task_id,
                               kind="answer", source="user_confirmed", user_id=user_id)

    def get_answer(self, key: str, *, task_id: Optional[str] = None,
                   user_id: Optional[str] = None) -> Optional[MemoryRecord]:
        return self._store.get(Scope.TASK, f"answer:{key}", task_id=task_id, user_id=user_id)

    # ---- TaskState（任务状态记忆）----
    def set_task_state(self, key: str, value: Any, *, task_id: str) -> MemoryRecord:
        return self._store.put(Scope.TASK, f"state:{key}", value, task_id=task_id,
                               kind="task_state")

    def get_task_state(self, key: str, *, task_id: str) -> Optional[MemoryRecord]:
        return self._store.get(Scope.TASK, f"state:{key}", task_id=task_id)

    # ---- Policy（策略；不可被 Preference Learning 改变）----
    def set_policy(self, key: str, value: Any) -> MemoryRecord:
        return self._store.put(Scope.GLOBAL, f"policy:{key}", value, kind="policy",
                               source="system")

    def get_policy(self, key: str) -> Optional[MemoryRecord]:
        return self._store.get(Scope.GLOBAL, f"policy:{key}")

    # ---- ExecutionHistory（执行历史）----
    def set_execution(self, key: str, value: Any, *, task_id: str) -> MemoryRecord:
        return self._store.put(Scope.TASK, f"exec:{key}", value, task_id=task_id,
                               kind="execution_history", source="executor")

    def get_execution(self, key: str, *, task_id: str) -> Optional[MemoryRecord]:
        return self._store.get(Scope.TASK, f"exec:{key}", task_id=task_id)

    # ---- 通用查询 ----
    def query(self, q: MemoryQuery) -> List[MemoryRecord]:
        return self._store.query(q)
