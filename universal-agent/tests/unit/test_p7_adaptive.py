"""P7 — Adaptive Watch：按时间窗口调整扫描频率 + HOT WATCH + governor 约束。

规则（指令）：
  >30d  → 1–2/day
  15–30d → 3/day
  7–14d  → 4/day
  <7d    → 4–6/day
  HOT（价格快变/接近目标/库存风险）→ 更高频（受 governor 约束）
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from universal_agent.core.contracts import WatchTask


def _task(depart_days: int, hot: bool = False) -> WatchTask:
    depart = datetime.now(timezone.utc) + timedelta(days=depart_days)
    return WatchTask(
        id=f"t{depart_days}", type="watch", domain="flight",
        schedule={"timezone": "Asia/Shanghai", "baseline": ["09:00"]},
        meta={"target_depart": depart.isoformat(), "hot": hot},
    )


def test_adaptive_interval_by_horizon() -> None:
    """按出发天数选择扫描间隔。"""
    from universal_agent.coordinator.scheduler.rule_adaptive import RuleAdaptiveScheduler
    sched = RuleAdaptiveScheduler()
    # >30 天 → 每天 1-2 次（间隔 ≥ 12h）
    assert sched.interval_hours(_task(depart_days=45)) >= 12
    # 15-30 天 → 每天 3 次（间隔 8h）
    assert 7 <= sched.interval_hours(_task(depart_days=20)) <= 9
    # 7-14 天 → 每天 4 次（间隔 6h）
    assert 5 <= sched.interval_hours(_task(depart_days=10)) <= 7
    # <7 天 → 每天 4-6 次（间隔 ≤ 6h）
    assert sched.interval_hours(_task(depart_days=3)) <= 6


def test_hot_watch_shorter_interval() -> None:
    from universal_agent.coordinator.scheduler.rule_adaptive import RuleAdaptiveScheduler
    sched = RuleAdaptiveScheduler()
    normal = sched.interval_hours(_task(depart_days=10, hot=False))
    hot = sched.interval_hours(_task(depart_days=10, hot=True))
    assert hot < normal  # HOT 加速


def test_next_run_returns_future_datetime() -> None:
    from universal_agent.coordinator.scheduler.rule_adaptive import RuleAdaptiveScheduler
    sched = RuleAdaptiveScheduler()
    now = datetime.now(timezone.utc)
    nr = sched.next_run(_task(depart_days=10), last_scan_at=now)
    assert nr is not None
    assert nr.at > now


def test_governor_limits_hot_scan() -> None:
    """HOT 频率受 governor 预算约束（超限不再提前）。"""
    from universal_agent.adapters.health import ResourceGovernor
    from universal_agent.coordinator.scheduler.rule_adaptive import RuleAdaptiveScheduler
    sched = RuleAdaptiveScheduler()
    gov = ResourceGovernor(budget={"browser_calls": 2})
    gov.consume("browser_calls")
    gov.consume("browser_calls")
    # 预算耗尽 → 不调度额外扫描（返回 None 或较长间隔）
    assert sched.allowed_by_governor(gov, "browser_calls") is False
