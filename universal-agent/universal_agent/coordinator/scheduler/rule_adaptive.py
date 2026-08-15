"""RuleAdaptiveScheduler（P7）— 按时间窗口 + HOT 动态调整扫描频率。

规则（指令）：
  >30d   → 每天 1-2 次（间隔 12h）
  15-30d → 每天 3 次（间隔 8h）
  7-14d  → 每天 4 次（间隔 6h）
  <7d    → 每天 4-6 次（间隔 4h）
  HOT（价格快变/接近目标/库存风险）→ 间隔减半（受 governor 约束）

目标日期从 task.meta["target_depart"] 读取；HOT 从 task.meta["hot"]。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from ...core.contracts import WatchTask
from .adaptive import AdaptiveScheduler


class _NextRun:
    def __init__(self, at: datetime) -> None:
        self.at = at


class RuleAdaptiveScheduler(AdaptiveScheduler):
    def interval_hours(self, task: WatchTask) -> float:
        """按剩余天数返回扫描间隔（小时）。"""
        days = self._days_until_depart(task)
        if days > 30:
            hours = 12.0
        elif days > 14:
            hours = 8.0
        elif days > 7:
            hours = 6.0
        else:
            hours = 4.0
        if self._is_hot(task):
            hours = max(hours / 2, 1.0)
        return hours

    def next_run(self, task: WatchTask, last_scan_at=None,
                 observations=None) -> Optional[object]:
        """基于上次扫描时间 + 自适应间隔计算下次运行。"""
        base = last_scan_at or task.last_scan_at or datetime.now(timezone.utc)
        if base.tzinfo is None:
            base = base.replace(tzinfo=timezone.utc)
        return _NextRun(base + timedelta(hours=self.interval_hours(task)))

    def allowed_by_governor(self, governor, resource: str) -> bool:
        """HOT 加速受 governor 预算约束。"""
        return bool(governor is not None and governor.can(resource))

    # ---- helpers ----
    def _days_until_depart(self, task: WatchTask) -> int:
        raw = (task.meta or {}).get("target_depart")
        if not raw:
            return 30  # 无目标日期 → 默认 30 天档
        try:
            depart = datetime.fromisoformat(raw)
            if depart.tzinfo is None:
                depart = depart.replace(tzinfo=timezone.utc)
            return max(int((depart - datetime.now(timezone.utc)).days), 0)
        except (ValueError, TypeError):
            return 30

    def _is_hot(self, task: WatchTask) -> bool:
        return bool((task.meta or {}).get("hot", False))
