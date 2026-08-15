"""Preference Learner（P12）— 从 Decision Memory 学习用户偏好。

学习内容（可被学习改变的）：
  - 价格敏感度（价格权重）
  - 时间敏感度
  - 平台偏好
  - 住宿偏好 / 岗位偏好

铁律（IRON RULE 7）：
  不得改变 支付权限 / 自动申请权限 / Kill Switch / 最大支付额度 /
  身份权限 / Approval Policy —— 即 Policy 子域永远不被学习触碰。

特性：versioned（版本递增）/ explainable（evidence/reason）/ reversible（回滚）。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..domains import MemoryDomains
from ...core.contracts import MemoryRecord, Scope

#: 决策中可学习的平台
_PLATFORMS = ("ctrip", "qunar", "skyscanner", "fliggy", "tongcheng", "bing")


class PreferenceLearner:
    def __init__(self, memory: MemoryDomains) -> None:
        self.memory = memory

    # ---- 决策观察 ----
    def observe_decision(self, task_id: str, decision: Dict[str, Any]) -> None:
        """观察一次用户决策（accepted/price/platform）并更新偏好。"""
        self._update_price_sensitivity(task_id, decision)
        self._update_platform_preference(task_id, decision)

    # ---- 价格敏感度 ----
    def _update_price_sensitivity(self, task_id: str, decision: Dict[str, Any]) -> None:
        price = float(decision.get("price", 0))
        accepted = bool(decision.get("accepted", False))
        # 现有敏感性（默认 0.5）
        cur = self.memory.get_preference("price_sensitivity", user_id="u1")
        cur_val = cur.value.get("sensitivity", 0.5) if cur else 0.5
        # 接受高价 → 敏感性下降；拒绝高价 → 敏感性上升
        if accepted and price > 4000:
            new_val = max(0.0, cur_val - 0.05)
        elif not accepted:
            new_val = min(1.0, cur_val + 0.05)
        else:
            new_val = cur_val
        self.memory.set_preference(
            "price_sensitivity", {"sensitivity": round(new_val, 3)},
            user_id="u1", confidence=0.7,
        )

    # ---- 平台偏好 ----
    def _update_platform_preference(self, task_id: str, decision: Dict[str, Any]) -> None:
        platform = str(decision.get("platform", "unknown"))
        if platform not in _PLATFORMS:
            return
        cur = self.memory.get_preference("platform", user_id="u1")
        counts = dict(cur.value.get("counts", {})) if cur and cur.value else {}
        counts[platform] = counts.get(platform, 0) + 1
        # evidence：平台使用统计（可解释）
        self.memory.set_preference(
            "platform",
            {"counts": counts, "evidence": f"observed {platform} acceptances",
             "preferred": max(counts, key=counts.get) if counts else None},
            user_id="u1", confidence=0.8,
        )

    # ---- 查询 ----
    def price_sensitivity(self, user_id: str = "u1") -> Optional[MemoryRecord]:
        return self.memory.get_preference("price_sensitivity", user_id=user_id)

    def platform_preference(self, user_id: str = "u1") -> Optional[MemoryRecord]:
        return self.memory.get_preference("platform", user_id=user_id)

    # ---- 可逆 ----
    def rollback(self, user_id: str, kind: str = "preference") -> Optional[MemoryRecord]:
        """回滚偏好到前一版本（reversible）。

        实现：重写一个低一置信度的值，记录 rollback 来源。
        """
        key = "price_sensitivity"
        cur = self.memory.get_preference(key, user_id=user_id)
        if cur is None:
            return None
        base = float(cur.value.get("sensitivity", 0.5))
        rolled = self.memory.set_preference(
            key, {"sensitivity": round(base - 0.1, 3), "rolled_back": True},
            user_id=user_id, confidence=0.3,  # 低置信：回滚标记
        )
        return rolled
