"""Baseline Scheduler（§15 + P0.1 修复）— IANA 时区 + DST 安全 + misfire。

规则：
- 数据库内部：UTC aware datetime
- Task 配置：IANA timezone（zoneinfo.ZoneInfo，DST-safe）
- due 判定：datetime 比较（task.next_scan_at <= now_utc）
- MisfirePolicy: SKIP / RUN_ONCE（默认）/ CATCH_UP_LIMITED
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from enum import Enum
from typing import List, Optional

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ...core.contracts import WatchTask


class MisfirePolicy(str, Enum):
    SKIP = "SKIP"
    RUN_ONCE = "RUN_ONCE"
    CATCH_UP_LIMITED = "CATCH_UP_LIMITED"


@dataclass
class NextRun:
    at: datetime
    due_in_seconds: int


@dataclass
class MissedRun:
    """错过的 baseline 运行点（供 misfire 补跑）。"""
    scheduled_at: datetime
    policy: MisfirePolicy


def _parse_hhmm(value: str) -> time:
    hh, mm = value.split(":")
    return time(int(hh), int(mm))


def resolve_tz(task: WatchTask) -> ZoneInfo:
    """解析 task IANA 时区；无效则抛 ValueError（fail closed）。"""
    tz_name = (task.schedule.timezone or "Asia/Shanghai").strip()
    try:
        return ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, KeyError) as exc:
        raise ValueError(f"invalid IANA timezone: {tz_name!r}") from exc


class BaselineScheduler:
    """Pure deterministic scheduler — no IO, DST-safe."""

    def __init__(self) -> None:
        # 无固定时区：每个 task 用自身 IANA 时区
        pass

    def baseline_times(self, task: WatchTask) -> List[time]:
        return [_parse_hhmm(t) for t in task.schedule.baseline]

    def next_run(self, task: WatchTask, now: Optional[datetime] = None) -> Optional[NextRun]:
        """下一个 baseline 时间（严格晚于 now）。返回 UTC aware datetime。"""
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        now = now.astimezone(timezone.utc)
        if not task.schedule.baseline:
            return None
        tz = resolve_tz(task)
        local = now.astimezone(tz)
        today = local.date()

        candidates = self._candidates_on(task, today, after=local.time())
        day_offset = 0
        while not candidates and day_offset < 8:
            day_offset += 1
            candidates = self._candidates_on(task, today + timedelta(days=day_offset))
        if not candidates:
            return None
        nxt_local_time = candidates[0]
        # DST-safe: 用 tz.localize 语义 → 构造本地 naive → astimezone(UTC)
        at_local = datetime.combine(today + timedelta(days=day_offset), nxt_local_time)
        at_utc = at_local.replace(tzinfo=tz).astimezone(timezone.utc)
        return NextRun(at=at_utc, due_in_seconds=max(0, int((at_utc - now).total_seconds())))

    def missed_run(self, task: WatchTask, now: Optional[datetime] = None,
                   policy: MisfirePolicy = MisfirePolicy.RUN_ONCE,
                   max_catch_up: int = 1) -> Optional[MissedRun]:
        """判断自 last_scan 起是否错过了 baseline；按 policy 决定补跑。"""
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        now = now.astimezone(timezone.utc)
        if policy == MisfirePolicy.SKIP:
            return None
        if task.last_scan_at is None:
            return None  # 从未扫描，由正常调度接管
        last = task.last_scan_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        last = last.astimezone(timezone.utc)

        tz = resolve_tz(task)
        missed: List[datetime] = []
        # 从 last_scan 到 now 之间，逐日找 baseline 时刻（在 last 之后且 <= now）
        day = last.astimezone(tz).date()
        guard = 0
        while day <= now.astimezone(tz).date() and guard < 32:
            for bt in self.baseline_times(task):
                at_local = datetime.combine(day, bt)
                at_utc = at_local.replace(tzinfo=tz).astimezone(timezone.utc)
                if last < at_utc <= now:
                    missed.append(at_utc)
            day += timedelta(days=1)
            guard += 1

        if not missed:
            return None
        if policy == MisfirePolicy.CATCH_UP_LIMITED:
            missed = missed[-max_catch_up:]
        return MissedRun(scheduled_at=missed[0], policy=policy)

    def _candidates_on(self, task: WatchTask, day: date,
                       after: Optional[time] = None) -> List[time]:
        out = []
        for t in self.baseline_times(task):
            if after is None or t > after:
                out.append(t)
        return sorted(out)
