"""coordinator package — orchestration of watch lifecycle."""
from __future__ import annotations

from .checkpoint import Checkpoint
from .scheduler import BaselineScheduler, NextRun
from .task_registry import TaskRegistry
from .watch_manager import WatchManager

__all__ = ["BaselineScheduler", "Checkpoint", "NextRun", "TaskRegistry", "WatchManager"]
