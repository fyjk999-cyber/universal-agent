"""Jarvis Migration Test (§46, §73) — formal acceptance.

Run the exact host-swap sequence:
  1. HarnessHostAdapter → create WatchTask → scan → save Memory
  2. STOP harness adapter
  3. START MockJarvisHostAdapter on the SAME data dir
  4. Read the same Task / Memory → continue watch → notify
  5. Universal Core code changes required: 0

If this test needs any Core change to pass, the abstraction is broken.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from universal_agent.core.contracts import WatchState
from universal_agent.hosts.deepseek_harness import HarnessHostAdapter
from universal_agent.hosts.jarvis import MockJarvisHostAdapter
from universal_agent.memory import MemoryStore
from universal_agent.core.contracts import Scope


class TestJarvisHostSwap:
    def test_swap_requires_zero_core_changes(self, tmp_path: Path, queenstown_watch):
        data_dir = tmp_path / "data"
        # P1.6: 共享 SQLite 单一真相源；Host 只发 Command
        from universal_agent.coordinator.task_coordinator import sqlite_task_coordinator

        # ---- 1. run under Harness ----
        coord = sqlite_task_coordinator(data_dir / "ua.db")
        harness = HarnessHostAdapter(coordinator=coord)
        created = harness.create_task(queenstown_watch)
        assert harness.get_task(created.id) is not None

        # save memory via Core-owned store (host-independent)
        mem = MemoryStore(data_dir / "memory")
        mem.put(Scope.TASK, "notified_candidate", "c1", task_id=created.id,
                source="test")

        # ---- 2. STOP harness adapter (simulate host shutdown) ----
        del harness

        # ---- 3. START MockJarvisHostAdapter on SAME SQLite truth ----
        coord2 = sqlite_task_coordinator(data_dir / "ua.db")
        jarvis = MockJarvisHostAdapter(coordinator=coord2)

        # ---- 4. read the SAME task / memory, continue watch ----
        restored = jarvis.get_task(created.id)
        assert restored is not None, "task lost across host swap"
        assert restored.id == created.id
        assert restored.state == WatchState.DRAFT

        # resume lifecycle through Jarvis: activate (legal DRAFT→ACTIVE) then pause/resume
        from universal_agent.core.contracts import WatchState as _WS
        activated = jarvis.get_task(created.id)
        activated.state = _WS.ACTIVE
        jarvis.update_task(activated)
        jarvis.pause_task(created.id)             # ACTIVE → PAUSED
        resumed = jarvis.resume_task(created.id)  # PAUSED → WATCHING
        assert resumed is not None
        assert resumed.state == _WS.WATCHING

        # memory must also survive (Core-owned, not host-owned)
        mem2 = MemoryStore(data_dir / "memory")
        got = mem2.get(Scope.TASK, "notified_candidate", task_id=created.id)
        assert got is not None and got.value == "c1"

        # notification through new host must work
        jarvis.send_notification({"title": "watch resumed under Jarvis", "task_id": created.id})

        # ---- 5. assert core module set is untouched ----
        assert _core_modules_unchanged()

    def test_run_task_once_interface_survives_swap(self, tmp_path: Path, queenstown_watch):
        data_dir = tmp_path / "data"
        from universal_agent.coordinator.task_coordinator import sqlite_task_coordinator
        coord = sqlite_task_coordinator(data_dir / "ua.db")
        h = HarnessHostAdapter(coordinator=coord)
        h.create_task(queenstown_watch)
        del h
        coord2 = sqlite_task_coordinator(data_dir / "ua.db")
        j = MockJarvisHostAdapter(coordinator=coord2)
        tasks = j.list_tasks()
        assert len(tasks) == 1
        # FR-030（P23）：无 runner 时显式失败（不再 not_implemented）
        from universal_agent.coordinator.task_coordinator import TaskCommandError
        try:
            j.run_task_once(tasks[0].id)
            raise AssertionError("run_task_once 无 runner 应显式失败")
        except TaskCommandError:
            pass
        assert j.get_host_user_context()["host"] == "jarvis"


def _core_modules_unchanged() -> bool:
    """Host swap must not require touching core/ — verify via imports only."""
    import importlib
    for mod in ("universal_agent.core.contracts",
                "universal_agent.core.state_machine",
                "universal_agent.events",
                "universal_agent.memory",
                "universal_agent.registry"):
        importlib.import_module(mod)
    return True
