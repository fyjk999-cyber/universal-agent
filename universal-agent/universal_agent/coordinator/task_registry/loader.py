"""Task file loader — reads tasks/*.yaml into TaskSpec (§13 layout)."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml

from ...core.contracts import TaskSpec, WatchTask


def load_task_spec(path: Path) -> TaskSpec:
    """Load a task YAML into TaskSpec.

    Layout (§13): `task:` holds identity fields; `lifecycle`, `schedule`,
    `search_space`, `notify_if`, `meta` may sit at top level next to `task:`
    and are merged into the spec.
    """
    raw = yaml.safe_load(Path(path).read_text("utf-8"))
    data = _merge(raw)
    return TaskSpec.model_validate(data)


def load_watch_task(path: Path) -> WatchTask:
    return WatchTask(**load_task_spec(path).model_dump())


def _merge(raw: Dict[str, Any]) -> Dict[str, Any]:
    base = dict(raw.get("task") or {})
    for key in ("lifecycle", "schedule", "search_space", "notify_if", "meta"):
        if key in raw:
            base[key] = raw[key]
    return base
