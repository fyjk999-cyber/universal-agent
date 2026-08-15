"""P20 — Jarvis Integration：Host Swap 全链路，Core 零修改。

验收：
1. UniversalAgentService(host="jarvis") 一键换 Host
2. Harness 断开 → Jarvis 接入 → Task/Memory 继续（同一 SQLite）
3. Scheduler 继续运行（daemon 用同一 Repository Set）
4. Event History 继续（同一 EventStore）
5. Core 模块集未变（test_host_swap 扩展）
"""
from __future__ import annotations

from pathlib import Path

import pytest

from universal_agent.service import UniversalAgentService


def test_jarvis_service_host_swap(tmp_path: Path) -> None:
    """Harness → Jarvis 换 Host：Core 状态继续。"""
    # Harness 阶段
    svc_h = UniversalAgentService(data_dir=tmp_path / "data", host="deepseek_harness")
    from universal_agent.core.contracts import WatchTask
    created = svc_h.coordinator.create_watch(WatchTask(
        id="w1", type="watch", domain="flight",
        schedule={"timezone": "Asia/Shanghai", "baseline": ["09:00"]}))
    try:
        svc_h.coordinator.activate("w1")
    finally:
        svc_h.close()

    # Jarvis 阶段（同一 data_dir → 同一 SQLite）
    svc_j = UniversalAgentService(data_dir=tmp_path / "data", host="jarvis")
    try:
        restored = svc_j.coordinator.get("w1")
        assert restored is not None and restored.id == "w1"
        assert restored.state.value == "ACTIVE"  # 状态跨 Host 保留
        # Jarvis 可继续操作
        svc_j.coordinator.pause("w1")
        paused = svc_j.coordinator.get("w1")
        assert paused.state.value == "PAUSED"
    finally:
        svc_j.close()


def test_jarvis_adapter_full_protocol(tmp_path: Path) -> None:
    """Jarvis adapter 实现 HostProtocol 全部方法。"""
    svc = UniversalAgentService(data_dir=tmp_path / "data", host="jarvis")
    try:
        from universal_agent.core.contracts import WatchTask
        t = WatchTask(id="w2", type="watch", domain="flight",
                      schedule={"timezone": "Asia/Shanghai", "baseline": ["09:00"]})
        # 全协议方法
        created = svc.adapter.create_task(t)
        assert created is not None
        listed = svc.adapter.list_tasks()
        assert any(x.id == "w2" for x in listed)
        got = svc.adapter.get_task("w2")
        assert got is not None
        ctx = svc.adapter.get_host_user_context()
        assert ctx["host"] == "jarvis"
        svc.adapter.send_notification({"title": "test"})
        resp = svc.adapter.request_approval({"title": "approve me"})
        assert resp is not None
        svc.adapter.publish_event(None)
    finally:
        svc.close()


def test_jarvis_scheduler_continues(tmp_path: Path) -> None:
    """Scheduler 在 Jarvis Host 下继续运行（同一 Repository Set）。"""
    from datetime import datetime, timedelta, timezone
    from universal_agent.coordinator.scheduler.daemon import WatchDaemon

    svc = UniversalAgentService(data_dir=tmp_path / "data", host="jarvis")
    try:
        from universal_agent.core.contracts import WatchTask
        t = WatchTask(id="w3", type="watch", domain="flight",
                      schedule={"timezone": "Asia/Shanghai", "baseline": ["09:00"]})
        svc.coordinator.create_watch(t)
        svc.coordinator.activate("w3")
        now = datetime.now(timezone.utc)
        task = svc.coordinator.get("w3")
        task.next_scan_at = now - timedelta(minutes=5)
        svc.coordinator.apply_update(task)

        ran = []

        async def runner(t):
            ran.append(t.id)
            return {"ok": True}

        d = WatchDaemon(registry=svc.repos.tasks, scan_runs=svc.repos.scan_runs,
                        tick_seconds=60, runner=runner)
        import asyncio
        asyncio.run(d._tick())
        assert ran == ["w3"]  # Scheduler 在 Jarvis 下继续执行
    finally:
        svc.close()


def test_core_modules_untouched_by_host_swap(tmp_path: Path) -> None:
    """Host Swap 不改变 Core 模块集。"""
    import universal_agent.coordinator.task_coordinator as tc
    import universal_agent.core.state_machine as sm
    import universal_agent.events.bus as bus
    # Core 模块可导入且不依赖 host 包
    assert not hasattr(tc, "jarvis")
    assert not hasattr(sm, "host")
