"""Source Health（P6）— 数据源健康动态跟踪。

状态机：
  HEALTHY → (连续失败 ≥ degrade_after) → DEGRADED
  DEGRADED → (连续失败 ≥ degrade_after*2) → UNAVAILABLE
  任一成功 → consecutive_failure=0，状态回升

跟踪：latency / success_rate / parser_success / price_consistency /
last_success / last_failure / consecutive_failure
"""
from __future__ import annotations

import time
from typing import Dict, Optional

from ...persistence.protocol import SourceHealthRepository

DEFAULT_DEGRADE_AFTER = 3


class SourceHealthTracker:
    def __init__(self, repo: SourceHealthRepository,
                 degrade_after: int = DEFAULT_DEGRADE_AFTER) -> None:
        self.repo = repo
        self.degrade_after = degrade_after

    def record_success(self, marketplace_id: str, latency_ms: Optional[float] = None,
                       parser_ok: bool = True, price_consistent: bool = True) -> Dict:
        h = self._base(marketplace_id)
        h["consecutive_failure"] = 0
        h["last_success"] = time.time()
        n = h.get("success_count", 0) + 1
        f = h.get("failure_count", 0)
        h["success_count"] = n
        h["success_rate"] = round(n / max(n + f, 1), 3)
        if latency_ms is not None:
            prev = h.get("avg_latency_ms") or 0
            c = h.get("sample_count", 0) + 1
            h["avg_latency_ms"] = round((prev * (c - 1) + latency_ms) / c, 1)
            h["sample_count"] = c
        h["parser_success"] = parser_ok
        h["price_consistency"] = price_consistent
        h["status"] = self._status_from_failures(0)
        self.repo.set(marketplace_id, h)
        return h

    def record_failure(self, marketplace_id: str, error: str = "") -> Dict:
        h = self._base(marketplace_id)
        h["consecutive_failure"] = h.get("consecutive_failure", 0) + 1
        h["last_failure"] = time.time()
        h["last_error"] = error
        h["failure_count"] = h.get("failure_count", 0) + 1
        n = h.get("success_count", 0)
        f = h.get("failure_count", 0)
        h["success_rate"] = round(n / max(n + f, 1), 3)
        h["status"] = self._status_from_failures(h["consecutive_failure"])
        self.repo.set(marketplace_id, h)
        return h

    def get(self, marketplace_id: str) -> Optional[Dict]:
        return self.repo.get(marketplace_id)

    def list(self) -> list:
        return self.repo.list()

    def _status_from_failures(self, consecutive: int) -> str:
        if consecutive >= self.degrade_after * 2:
            return "UNAVAILABLE"
        if consecutive >= self.degrade_after:
            return "DEGRADED"
        return "HEALTHY"

    def _base(self, marketplace_id: str) -> Dict:
        return self.repo.get(marketplace_id) or {
            "marketplace_id": marketplace_id,
            "status": "HEALTHY",
            "success_rate": 1.0,
            "avg_latency_ms": None,
            "consecutive_failure": 0,
            "success_count": 0,
            "failure_count": 0,
            "sample_count": 0,
            "parser_success": True,
            "price_consistency": True,
            "last_success": None,
            "last_failure": None,
            "last_error": "",
        }
