"""Shared pytest fixtures."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# ensure universal-agent package is importable
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from universal_agent.core.contracts import (  # noqa: E402
    Lifecycle,
    Schedule,
    SearchSpace,
    TaskSpec,
    TaskType,
    WatchTask,
)


@pytest.fixture
def queenstown_spec() -> TaskSpec:
    return TaskSpec(
        id="queenstown-travel-watch",
        type=TaskType.WATCH,
        domain="travel",
        lifecycle=Lifecycle(starts_at="2026-08-14", expires_at="2026-09-03"),
        schedule=Schedule(timezone="Asia/Shanghai",
                          baseline=["09:00", "15:00", "21:00"], adaptive=True),
        search_space=SearchSpace(
            origin=["HGH", "PVG", "SHA"],
            destination=["ZQN"],
            departure={"start": "2026-08-30", "end": "2026-09-03"},
            nights={"min": 6, "preferred": 7, "max": 8},
        ),
        notify_if={"price_drop_cny_gte": 300, "historical_low": True},
    )


@pytest.fixture
def queenstown_watch(queenstown_spec: TaskSpec) -> WatchTask:
    return WatchTask(**queenstown_spec.model_dump())
