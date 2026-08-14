"""Queenstown acceptance task load test (§67)."""
from __future__ import annotations

from pathlib import Path

from universal_agent.coordinator.task_registry import load_task_spec, load_watch_task
from universal_agent.core.contracts import TaskType, WatchState

TASK_FILE = Path(__file__).resolve().parent.parent.parent / "tasks" / "queenstown-travel-watch.yaml"


class TestQueenstownTask:
    def test_spec_loads(self):
        spec = load_task_spec(TASK_FILE)
        assert spec.id == "queenstown-travel-watch"
        assert spec.type == TaskType.WATCH
        assert spec.domain == "travel"
        assert spec.search_space.origin == ["HGH", "PVG", "SHA"]
        assert spec.search_space.destination == ["ZQN"]
        assert spec.search_space.nights["preferred"] == 7
        assert spec.schedule.baseline == ["09:00", "15:00", "21:00"]
        assert spec.lifecycle.expires_at.isoformat() == "2026-09-03"

    def test_watch_task_from_file(self):
        task = load_watch_task(TASK_FILE)
        assert task.state == WatchState.DRAFT

    def test_trigger_rules(self):
        spec = load_task_spec(TASK_FILE)
        assert spec.notify_if.price_drop_cny_gte == 300
        assert spec.notify_if.historical_low is True
