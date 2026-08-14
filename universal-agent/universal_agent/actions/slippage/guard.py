"""Price Slippage Guard (§39) — 确认价 vs 执行价差异保护.

规则示例: max_slippage_cny=100 / max_slippage_percent=2
确认 ¥4380 → 执行变 ¥4750 → ABORT.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class SlippageResult:
    allowed: bool
    confirmed: float
    actual: float
    delta_cny: float
    delta_percent: float
    reason: str = ""


class SlippageGuard:
    def check(self, confirmed: float, actual: float,
              max_cny: Optional[float] = None,
              max_percent: Optional[float] = None) -> SlippageResult:
        """返回是否允许继续；超限 → allowed=False + reason."""
        delta = actual - confirmed
        percent = (delta / confirmed * 100.0) if confirmed else 0.0
        if max_cny is not None and delta > max_cny:
            return SlippageResult(
                allowed=False, confirmed=confirmed, actual=actual,
                delta_cny=delta, delta_percent=percent,
                reason=f"slippage ¥{delta:.0f} > max ¥{max_cny:.0f}")
        if max_percent is not None and percent > max_percent:
            return SlippageResult(
                allowed=False, confirmed=confirmed, actual=actual,
                delta_cny=delta, delta_percent=percent,
                reason=f"slippage {percent:.2f}% > max {max_percent:.2f}%")
        return SlippageResult(allowed=True, confirmed=confirmed, actual=actual,
                              delta_cny=delta, delta_percent=percent)
