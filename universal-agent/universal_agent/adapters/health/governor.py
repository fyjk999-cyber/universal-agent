"""Resource Governor（P6）— 资源配额（防止每次全平台深度全扫）。

预算：api_calls / browser_calls / llm_tokens / runtime / verification_budget /
money_cost。consume() 超限拒绝（fail-closed：未知资源默认拒绝）。
"""
from __future__ import annotations

from typing import Dict


class ResourceGovernor:
    def __init__(self, budget: Dict[str, float]) -> None:
        self._budget = dict(budget)
        self._used: Dict[str, float] = {k: 0.0 for k in self._budget}

    def consume(self, resource: str, amount: float = 1) -> bool:
        """尝试消耗；超限/未知资源 → False。"""
        if resource not in self._budget:
            return False  # fail-closed：未预算资源不放行
        if self._used[resource] + amount > self._budget[resource]:
            return False
        self._used[resource] += amount
        return True

    def can(self, resource: str, amount: float = 1) -> bool:
        if resource not in self._budget:
            return False
        return self._used[resource] + amount <= self._budget[resource]

    def remaining(self, resource: str) -> float:
        if resource not in self._budget:
            return 0.0
        return max(self._budget[resource] - self._used[resource], 0.0)

    def reset(self, resource: Optional[str] = None) -> None:
        if resource is None:
            self._used = {k: 0.0 for k in self._budget}
        elif resource in self._used:
            self._used[resource] = 0.0

    def snapshot(self) -> Dict[str, Dict[str, float]]:
        return {k: {"budget": self._budget[k], "used": self._used[k]}
                for k in self._budget}
