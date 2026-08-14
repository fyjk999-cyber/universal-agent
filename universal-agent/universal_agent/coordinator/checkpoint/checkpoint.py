"""Checkpoint — process-restart recovery for scheduled watches (§60, §72)."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from ...core.contracts import utc_now

log = logging.getLogger("ua.coordinator.checkpoint")


@dataclass
class Checkpoint:
    """Lightweight runtime snapshot so watches resume after restart.

    Phase 1: JSON file under data dir. Truth stays in TaskRegistry; this only
    records scheduler heartbeat + which tasks were mid-cycle.
    """

    path: Path
    data: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text("utf-8"))
            except Exception:  # noqa: BLE001
                log.warning("checkpoint corrupt; resetting")

    def mark(self, key: str, value: Any) -> None:
        self.data[key] = value
        self.data["_updated_at"] = utc_now().isoformat()
        self._flush()

    def mark_task_started(self, task_id: str, cycle: str) -> None:
        tasks = self.data.setdefault("in_flight", {})
        tasks[task_id] = {"cycle": cycle, "started_at": utc_now().isoformat()}
        self._flush()

    def mark_task_done(self, task_id: str) -> None:
        self.data.setdefault("in_flight", {}).pop(task_id, None)
        self._flush()

    def in_flight(self) -> Dict[str, Any]:
        return dict(self.data.get("in_flight", {}))

    def _flush(self) -> None:
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), "utf-8")
