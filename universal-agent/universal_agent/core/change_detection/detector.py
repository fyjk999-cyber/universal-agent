"""Material change detection (§32, §71).

Compares current quote against the last observed quote for the same offer.
Only material changes (price delta beyond threshold) count as a change —
identical price must NOT re-trigger notification.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ...core.contracts import Quote


@dataclass
class ChangeResult:
    changed: bool
    old_price: Optional[float] = None
    new_price: Optional[float] = None
    delta_cny: float = 0.0
    delta_percent: float = 0.0


def detect_material_change(new_quote: Quote,
                           previous_quote: Optional[Quote],
                           min_delta_cny: float = 50.0,
                           min_delta_percent: float = 0.5) -> ChangeResult:
    if previous_quote is None:
        return ChangeResult(changed=True, new_price=new_quote.price.amount)
    old = previous_quote.price.amount
    new = new_quote.price.amount
    delta = new - old
    percent = (delta / old * 100.0) if old else 0.0
    changed = abs(delta) >= min_delta_cny or abs(percent) >= min_delta_percent
    return ChangeResult(changed=changed, old_price=old, new_price=new,
                        delta_cny=delta, delta_percent=percent)
