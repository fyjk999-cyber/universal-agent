"""coordinator.task_registry package."""
from __future__ import annotations

from .loader import load_task_spec, load_watch_task
from .registry import TaskRegistry

__all__ = ["TaskRegistry", "load_task_spec", "load_watch_task"]
