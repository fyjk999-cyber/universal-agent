"""P0.1 回归测试：Scheduler 时区 / DST / due 判定 / misfire。

规则（§P0.1）：
- 数据库内部 UTC aware datetime
- Task 配置 IANA timezone（zoneinfo.ZoneInfo）
- due 判定用 datetime 比较（task.next_scan_at <= now_utc），禁止 HH:MM 字符串
- DST-safe（Asia/Shanghai 无 DST；America/New_York 有 DST）
- MisfirePolicy: RUN_ONCE（默认）/ SKIP / CATCH_UP_LIMITED
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from universal_agent.coordinator.scheduler.baseline import BaselineScheduler, MisfirePolicy
from universal_agent.coordinator.task_registry import TaskRegistry
from universal_agent.core.contracts import WatchState, WatchTask


def _task(tz: str = "Asia/Shanghai", baseline: list[str] | None = None) -> WatchTask:
    return WatchTask(
        id="t1", type="watch", domain="flight",
        schedule={"timezone": tz, "baseline": baseline or ["09:00", "15:00", "21:00"]},
        state=WatchState.WATCHING,
    )


class TestTimezone:
    def test_next_run_in_task_timezone(self):
        """next_run 必须使用 task.schedule.timezone（IANA），而非 UTC。"""
        sch = BaselineScheduler()  # 内部应解析 task 时区
        task = _task(tz="Asia/Shanghai", baseline=["09:00"])
        # UTC 08:00 = Shanghai 16:00 → 下一个 baseline 是明天 09:00 Shanghai
        now = datetime(2026, 8, 14, 8, 0, tzinfo=timezone.utc)
        nxt = sch.next_run(task, now)
        assert nxt is not None
        # 转换到上海时区应为 09:00（当地），日期为 2026-08-15
        sh = nxt.at.astimezone(__import__("zoneinfo").ZoneInfo("Asia/Shanghai"))
        assert sh.hour == 9
        assert sh.date().isoformat() == "2026-08-15"

    def test_ny_dst_safety(self):
        """America/New_York 跨 DST：3 月/11 月切换时 next_run 必须安全。"""
        sch = BaselineScheduler()
        task = _task(tz="America/New_York", baseline=["09:00"])
        # 2026-11-01 DST 结束（fall back）前后各测一次
        before = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)
        after = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
        for now in (before, after):
            nxt = sch.next_run(task, now)
            assert nxt is not None
            ny = nxt.at.astimezone(__import__("zoneinfo").ZoneInfo("America/New_York"))
            assert ny.hour == 9
            assert ny.utcoffset() is not None  # 时区感知，无 naive datetime

    def test_invalid_timezone_rejected(self):
        sch = BaselineScheduler()
        task = _task(tz="Not/AZone", baseline=["09:00"])
        with pytest.raises(Exception):
            sch.next_run(task)


class TestDueComparison:
    def test_due_uses_datetime_not_string(self):
        """due_tasks 用 datetime 比较，杜绝 '09:00'<='21:00' 字符串比较。"""
        reg = TaskRegistry(Path("/tmp/ua-test-reg") / "r1")
        task = _task()
        # next_scan_at = 昨天 21:00 Shanghai → 已到期（现在是今天）
        from zoneinfo import ZoneInfo
        yesterday_21 = datetime(2026, 8, 13, 21, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        task.next_scan_at = yesterday_21
        reg.create(task)
        now = datetime(2026, 8, 14, 1, 0, tzinfo=timezone.utc)
        # 旧字符串比较：now.strftime("%H:%M")="01:00" < "21:00" → 判定未到期（错误）
        # 新比较：next_scan_at(13日21:00上海=13日13:00UTC) <= now(14日01:00UTC) → 到期
        assert reg.due_tasks_utc(now) == [task.id]


class TestMisfire:
    def test_run_once_catches_missed_run(self):
        """默认 RUN_ONCE：错过扫描时间 → 立即补跑一次。"""
        sch = BaselineScheduler()
        task = _task(baseline=["09:00"])
        # 上次扫描：昨天 09:00 上海；现在上海 18:30 → 今天 09:00/15:00 已错过
        task.last_scan_at = datetime(2026, 8, 13, 1, 0, tzinfo=timezone.utc)
        now = datetime(2026, 8, 14, 10, 30, tzinfo=timezone.utc)  # 上海 18:30
        missed = sch.missed_run(task, now, MisfirePolicy.RUN_ONCE)
        assert missed is not None  # 有错过的 baseline 需补跑

    def test_skip_does_not_catch_up(self):
        sch = BaselineScheduler()
        task = _task(baseline=["09:00"])
        task.last_scan_at = datetime(2026, 8, 13, 1, 0, tzinfo=timezone.utc)
        now = datetime(2026, 8, 14, 10, 30, tzinfo=timezone.utc)
        assert sch.missed_run(task, now, MisfirePolicy.SKIP) is None

    def test_catch_up_limited(self):
        sch = BaselineScheduler()
        task = _task(baseline=["09:00", "15:00"])
        task.last_scan_at = datetime(2026, 8, 13, 1, 0, tzinfo=timezone.utc)
        now = datetime(2026, 8, 14, 8, 0, tzinfo=timezone.utc)  # 上海 16:00，错过 09:00/15:00
        missed = sch.missed_run(task, now, MisfirePolicy.CATCH_UP_LIMITED, max_catch_up=1)
        assert missed is not None
        # 限制补跑 1 次而非全部

    def test_next_run_advances_across_midnight(self):
        sch = BaselineScheduler()
        task = _task(baseline=["23:00"])
        now = datetime(2026, 8, 14, 22, 30, tzinfo=timezone.utc)  # 上海 06:30 (8/15)
        nxt = sch.next_run(task, now)
        assert nxt is not None
        sh = nxt.at.astimezone(__import__("zoneinfo").ZoneInfo("Asia/Shanghai"))
        assert sh.hour == 23
        assert sh.date().isoformat() == "2026-08-15"  # 当天 23:00 尚未过
