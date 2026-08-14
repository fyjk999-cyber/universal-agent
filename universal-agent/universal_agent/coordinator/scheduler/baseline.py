"""Baseline Scheduler (§15) — Phase 1 must complete this.

Given a task's baseline times ["09:00","15:00","21:00"], computes the next
scan time. Adaptive Scheduler only exposes an interface + base rules for now.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import List, Optional

from ...core.contracts import WatchTask


@dataclass
class NextRun:
    at: datetime
    due_in_seconds: int


def _parse_hhmm(value: str) -> time:
    hh, mm = value.split(":")
    return time(int(hh), int(mm))


class BaselineScheduler:
    """Pure deterministic scheduler — no IO, easy to unit test and replay."""

    def __init__(self, tz: timezone = timezone.utc) -> None:
        self.tz = tz

    def baseline_times(self, task: WatchTask) -> List[time]:
        return [_parse_hhmm(t) for t in task.schedule.baseline]

    def next_run(self, task: WatchTask, now: Optional[datetime] = None) -> Optional[NextRun]:
        """Next baseline time strictly after `now` (defaults to utc now)."""
        now = now or datetime.now(timezone.utc)
        if not task.schedule.baseline:
            return None
        local = now.astimezone(self.tz)
        today = local.date()
        candidates = self._candidates_on(task, today, after=local.time())
        day_offset = 0
        while not candidates and day_offset < 8:
            day_offset += 1
            candidates = self._candidates_on(task, today + timedelta(days=day_offset))
        if not candidates:
            return None
        nxt = candidates[0]
        at = datetime.combine(today + timedelta(days=day_offset), nxt, tzinfo=self.tz)
        return NextRun(at=at, due_in_seconds=max(0, int((at - now).total_seconds())))

    def _candidates_on(self, task: WatchTask, day: date,
                       after: Optional[time] = None) -> List[time]:
        out = []
        for t in self.baseline_times(task):
            if after is None or t > after:
                out.append(t)
        return sorted(out)
