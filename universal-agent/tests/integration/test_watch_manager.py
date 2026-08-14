"""WatchManager + TaskRegistry + Checkpoint integration tests (§60, §72)."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from universal_agent.coordinator import Checkpoint, TaskRegistry, WatchManager
from universal_agent.core.contracts import WatchState
from universal_agent.events import EventEnvelope, EventType, InProcessEventBus


class TestWatchManager:
    @pytest.mark.asyncio
    async def test_lifecycle_create_activate_watching(self, tmp_path, queenstown_watch):
        bus = InProcessEventBus()
        events: list[EventEnvelope] = []

        async def collect(env: EventEnvelope):
            events.append(env)

        bus.subscribe(EventType.WATCH_STARTED, collect)
        bus.subscribe(EventType.WATCH_PAUSED, collect)

        reg = TaskRegistry(tmp_path / "registry")
        wm = WatchManager(reg, bus)

        created = wm.create_watch(queenstown_watch)
        assert created.state == WatchState.DRAFT

        active = wm.activate(created.id)
        assert active.state == WatchState.ACTIVE
        assert active.next_scan_at is not None

        watching = wm.start_watching(created.id)
        assert watching.state == WatchState.WATCHING

        paused = wm.pause(created.id)
        assert paused.state == WatchState.PAUSED
        assert paused.next_scan_at is None

        resumed = wm.resume(created.id)
        assert resumed.state == WatchState.WATCHING
        assert resumed.next_scan_at is not None

        # let async events drain
        await asyncio.sleep(0.05)
        types = {e.event_type for e in events}
        assert EventType.WATCH_STARTED in types
        assert EventType.WATCH_PAUSED in types
        await bus.close()

    def test_illegal_state_change_raises(self, tmp_path, queenstown_watch):
        reg = TaskRegistry(tmp_path / "registry")
        wm = WatchManager(reg, InProcessEventBus())
        created = wm.create_watch(queenstown_watch)
        # DRAFT -> WATCHING directly is illegal
        with pytest.raises(Exception):
            wm.start_watching(created.id)


class TestRestartRecovery:
    """Process-restart recovery: registry + checkpoint survive reload (§72)."""

    def test_registry_restores_after_reload(self, tmp_path, queenstown_watch):
        path = tmp_path / "reg"
        reg1 = TaskRegistry(path)
        task = reg1.create(queenstown_watch)
        reg1.update(task)
        del reg1

        reg2 = TaskRegistry(path)
        restored = reg2.get(task.id)
        assert restored is not None
        assert restored.id == task.id

    def test_checkpoint_tracks_in_flight_cycles(self, tmp_path):
        cp1 = Checkpoint(tmp_path / "cp.json")
        cp1.mark_task_started("t1", "cycle-2026-08-14-09")
        assert "t1" in cp1.in_flight()
        del cp1

        cp2 = Checkpoint(tmp_path / "cp.json")
        assert "t1" in cp2.in_flight()
        cp2.mark_task_done("t1")
        assert "t1" not in cp2.in_flight()

    def test_due_tasks(self, tmp_path, queenstown_watch):
        reg = TaskRegistry(tmp_path / "reg")
        task = reg.create(queenstown_watch)
        # only alive (active/watching) tasks are due
        from universal_agent.core.contracts import WatchState
        task.state = WatchState.WATCHING
        # simulate: schedule for 09:00 today
        from datetime import datetime, timezone
        task.next_scan_at = datetime(2026, 8, 14, 9, 0, tzinfo=timezone.utc)
        reg.update(task)
        due = reg.due_tasks("09:00")
        assert task.id in {t.id for t in due}
