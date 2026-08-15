"""Metrics（P4）— 持久化指标注册表。

指标清单（指令要求）：
  scan_duration / source_latency / source_success_rate / candidate_count /
  entity_resolution_rate / verification_rate / browser_calls / api_calls /
  llm_tokens / estimated_cost / notification_count / retry_count /
  lease_conflict_count / event_delivery_failure / action_block_count

JSON 持久化（跨重启保留）；increment/set/get/values。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, Optional, Union

log = logging.getLogger("ua.observability.metrics")

REQUIRED_METRICS = [
    "scan_duration",
    "source_latency",
    "source_success_rate",
    "candidate_count",
    "entity_resolution_rate",
    "verification_rate",
    "browser_calls",
    "api_calls",
    "llm_tokens",
    "estimated_cost",
    "notification_count",
    "retry_count",
    "lease_conflict_count",
    "event_delivery_failure",
    "action_block_count",
]

Number = Union[int, float]


class MetricsRegistry:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._values: Dict[str, Number] = {}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                self._values = json.loads(self.path.read_text("utf-8"))
            except Exception:  # noqa: BLE001
                log.warning("metrics.json corrupt; starting fresh")

    def _save(self) -> None:
        self.path.write_text(json.dumps(self._values, indent=2), "utf-8")

    def increment(self, key: str, delta: Number = 1) -> None:
        self._values[key] = self._values.get(key, 0) + delta
        self._save()

    def set(self, key: str, value: Number) -> None:
        self._values[key] = value
        self._save()

    def get(self, key: str) -> Optional[Number]:
        return self._values.get(key)

    def values(self) -> Dict[str, Number]:
        return dict(self._values)

    def snapshot(self) -> Dict[str, Number]:
        """全量快照（含未记录指标=0，供面板稳定展示）。"""
        out = {k: self._values.get(k, 0) for k in REQUIRED_METRICS}
        out.update(self._values)
        return out
