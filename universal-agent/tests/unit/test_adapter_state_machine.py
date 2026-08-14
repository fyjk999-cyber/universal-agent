"""Regression test: host adapters use Command mode + state machine (§14, P1.6).

Host adapter 不直接改 state；通过 TaskCoordinator → StateMachine → Repository。
"""
from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from universal_agent.core.contracts import WatchState
from universal_agent.core.state_machine import TransitionError
from universal_agent.hosts.deepseek_harness import HarnessHostAdapter
from universal_agent.hosts.jarvis import MockJarvisHostAdapter
from universal_agent.coordinator.task_registry import load_watch_task

TASK_FILE = Path(__file__).resolve().parent.parent.parent / "tasks" / "queenstown-travel-watch.yaml"


def _make_adapter(factory, tmp_path):
    from universal_agent.coordinator.task_coordinator import sqlite_task_coordinator
    coord = sqlite_task_coordinator(tmp_path / "ua.db")
    return factory(coordinator=coord)


def _activate(adapter, task_id):
    return adapter.coordinator.activate(task_id)


@pytest.mark.parametrize("factory", [
    HarnessHostAdapter,
    MockJarvisHostAdapter,
])
class TestAdapterStateMachine:
    def test_pause_uses_enum_and_validates(self, tmp_path, factory):
        adapter = _make_adapter(factory, tmp_path)
        wt = load_watch_task(TASK_FILE)
        adapter.create_task(wt)
        _activate(adapter, wt.id)
        with warnings.catch_warnings():
            warnings.simplefilter("error")  # any UserWarning → fail
            paused = adapter.pause_task(wt.id)
        assert paused.state == WatchState.PAUSED

    def test_resume_uses_enum(self, tmp_path, factory):
        adapter = _make_adapter(factory, tmp_path)
        wt = load_watch_task(TASK_FILE)
        adapter.create_task(wt)
        _activate(adapter, wt.id)
        adapter.pause_task(wt.id)
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            resumed = adapter.resume_task(wt.id)
        assert resumed.state == WatchState.WATCHING

    def test_resume_non_paused_is_noop(self, tmp_path, factory):
        """resume_task on a non-PAUSED task must not raise (adapter no-op)."""
        adapter = _make_adapter(factory, tmp_path)
        wt = load_watch_task(TASK_FILE)
        adapter.create_task(wt)
        _activate(adapter, wt.id)
        still = adapter.resume_task(wt.id)  # ACTIVE, not paused
        assert still.state == WatchState.ACTIVE

    def test_illegal_transition_raises(self, tmp_path, factory):
        """DRAFT → PAUSED is illegal; must raise TransitionError, not silently pass."""
        adapter = _make_adapter(factory, tmp_path)
        wt = load_watch_task(TASK_FILE)
        adapter.create_task(wt)  # stays DRAFT
        with pytest.raises(TransitionError):
            adapter.pause_task(wt.id)
