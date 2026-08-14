"""Baseline Scheduler tests (§15)."""
from __future__ import annotations

from datetime import datetime, timezone

from universal_agent.coordinator import BaselineScheduler
from universal_agent.core.contracts import Schedule, TaskSpec, TaskType


def _task(baseline: list[str], tz: str = "Asia/Shanghai") -> TaskSpec:
    return TaskSpec(id="t1", type=TaskType.WATCH, domain="flight",
                    schedule=Schedule(timezone=tz, baseline=baseline))


class TestBaselineScheduler:
    def test_next_run_within_same_day(self):
        sch = BaselineScheduler(tz=timezone.utc)
        t = _task(["09:00", "15:00", "21:00"])
        now = datetime(2026, 8, 14, 8, 0, tzinfo=timezone.utc)
        nxt = sch.next_run(t, now)
        assert nxt is not None
        assert nxt.at.hour == 9
        assert nxt.due_in_seconds == 3600

    def test_next_run_rolls_to_tomorrow(self):
        sch = BaselineScheduler(tz=timezone.utc)
        t = _task(["09:00", "15:00", "21:00"])
        now = datetime(2026, 8, 14, 22, 0, tzinfo=timezone.utc)
        nxt = sch.next_run(t, now)
        assert nxt is not None
        assert nxt.at.day == 15
        assert nxt.at.hour == 9

    def test_no_baseline_returns_none(self):
        sch = BaselineScheduler(tz=timezone.utc)
        t = _task([])
        assert sch.next_run(t) is None

    def test_baseline_times_parsed(self):
        sch = BaselineScheduler(tz=timezone.utc)
        t = _task(["09:00", "21:30"])
        times = sch.baseline_times(t)
        assert [x.hour for x in times] == [9, 21]
        assert times[1].minute == 30
