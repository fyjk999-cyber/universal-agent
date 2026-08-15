"""Railway 定时 Watch 集成测试（P23）— 12306 真实数据 + WatchDaemon + 持久化通知。"""
from __future__ import annotations

import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

BASE = Path(__file__).resolve().parent.parent.parent


async def _build_daemon(tmp_path: Path, tick: int = 3600):
    from universal_agent.apps.scheduler import _persistent_notifier, _railway_runner
    from universal_agent.coordinator.scheduler import load_watch_daemon

    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(BASE / "tasks" / "railway-watch.yaml", tasks_dir / "railway-watch.yaml")
    data_dir = tmp_path / "data"
    notifier = _persistent_notifier(data_dir)
    runner = _railway_runner(notifier=notifier)
    daemon = await load_watch_daemon(tasks_dir, data_dir, runner=runner,
                                     tick_seconds=tick)
    # 激活 + 强制任务到期（下一 tick 必须执行）
    from universal_agent.core.contracts import WatchState
    for t in daemon.registry.list():
        t.state = WatchState.ACTIVE
        t.next_scan_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        daemon.registry.update(t)
    return daemon, data_dir


class TestRailwayWatch:
    async def test_watch_scan_records_scanrun_and_persists_notification(
            self, tmp_path: Path):
        """WatchDaemon tick → Railway 扫描 → ScanRun + 通知持久化（SQLite）。"""
        from universal_agent.persistence import Database

        daemon, data_dir = await _build_daemon(tmp_path)
        await daemon._tick()

        # 1) ScanRun 必须被记录（Watch 持久化，RULE-003）
        runs = daemon.scan_runs.list_all()
        assert runs, "railway watch tick 必须产生 ScanRun"
        assert runs[0].task_id == "railway-shanghai-hangzhou"

        # 2) 12306 可达性判断：不可达/限流时为空结果也合法（fail-closed）
        db = Database(data_dir / "universal_agent.db")
        rows = db.query_all("SELECT * FROM notifications")
        # 机会出现 → 通知必须已持久化；无机会（售罄/限流）→ 无通知也合法
        # （本测试只断言：存在通知时其 payload 完整）
        for row in rows:
            import json
            payload = json.loads(row["data"])
            assert payload.get("event_type") == "OPPORTUNITY_DETECTED"
            assert payload.get("title")

    async def test_runner_skips_non_railway_domain(self):
        """多域共存：非 railway 任务被 runner 跳过，不误扫。"""
        from universal_agent.apps.scheduler import _railway_runner
        from universal_agent.core.contracts import TaskType, WatchTask

        runner = _railway_runner()
        t = WatchTask(id="x", type=TaskType.WATCH, domain="flight",
                      schedule={"timezone": "Asia/Shanghai"})
        out = await runner(t)
        assert out == {"skipped": "flight"}
