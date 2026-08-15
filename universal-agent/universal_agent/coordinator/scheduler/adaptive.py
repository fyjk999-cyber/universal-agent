"""Adaptive Scheduler — interface + base rules only (Phase 1, §15).

Full adaptive logic (learned intervals, price-velocity adjustments) lands in
Phase B/C after Observation history exists. P7 adds RuleAdaptiveScheduler.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from ...core.contracts import WatchTask


class AdaptiveScheduler(ABC):
    @abstractmethod
    def next_run(self, task: WatchTask, last_scan_at=None,
                 observations=None) -> Optional[object]:
        """Return a NextRun-like object or None."""


class NoOpAdaptiveScheduler(AdaptiveScheduler):
    """Phase 1: no adaptation — delegate to baseline."""

    def next_run(self, task: WatchTask, last_scan_at=None, observations=None) -> Optional[object]:
        return None
