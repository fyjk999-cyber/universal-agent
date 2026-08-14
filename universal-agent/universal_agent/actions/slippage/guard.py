"""Price Slippage Guard（§39 + P0.3 修复）— approved vs actual。

规则（P0.3）：
- 禁止 confirmed vs confirmed 自比较
- 执行前重新获取 actual_checkout_price
- SlippageGuard(approved_price, actual_checkout_price)
- 同时检查价格 / 币种 / 行李 / 退改 / 数量 / 日期 / 订单内容 → Material Change
- Material Change → ABORT 或重新 Approval
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class SlippageResult:
    allowed: bool
    approved: float
    actual: float
    delta_cny: float
    delta_percent: float
    reason: str = ""
    material_change: bool = False


class SlippageGuard:
    def check(self, approved: float, actual: float,
              max_cny: Optional[float] = None,
              max_percent: Optional[float] = None) -> SlippageResult:
        """价格滑移校验：approved 为批准价，actual 为执行前重取价。"""
        if approved is None or actual is None:
            return SlippageResult(allowed=False, approved=approved or 0,
                                  actual=actual or 0, delta_cny=0, delta_percent=0,
                                  reason="missing approved/actual price")
        delta = actual - approved
        percent = (delta / approved * 100.0) if approved else 0.0
        if max_cny is not None and delta > max_cny:
            return SlippageResult(
                allowed=False, approved=approved, actual=actual,
                delta_cny=delta, delta_percent=percent,
                reason=f"slippage ¥{delta:.0f} > max ¥{max_cny:.0f}")
        if max_percent is not None and percent > max_percent:
            return SlippageResult(
                allowed=False, approved=approved, actual=actual,
                delta_cny=delta, delta_percent=percent,
                reason=f"slippage {percent:.2f}% > max {max_percent:.2f}%")
        return SlippageResult(allowed=True, approved=approved, actual=actual,
                              delta_cny=delta, delta_percent=percent)

    def check_material(self, approved: Dict[str, Any],
                       actual: Dict[str, Any],
                       keys: Optional[list[str]] = None) -> SlippageResult:
        """Material Change 检查（P0.3）：比较批准快照 vs 执行前实际。

        keys 默认检查订单内容字段（不含 price —— 价格单独由 check() 处理，
        避免合法小幅价格波动被误判为材料变化）。
        """
        keys = keys or ["currency", "baggage", "refundable", "quantity",
                        "date", "flight", "room", "passenger"]
        changed_fields = [k for k in keys
                          if approved.get(k) != actual.get(k)
                          and k in approved and k in actual]
        material = len(changed_fields) > 0

        approved_price = approved.get("price")
        actual_price = actual.get("price")
        result = self.check(approved_price, actual_price,
                            max_cny=approved.get("max_slippage_cny"),
                            max_percent=approved.get("max_slippage_percent"))
        result.material_change = material
        if material and result.allowed:
            result.allowed = False
            result.reason = f"material change in fields: {changed_fields}"
        return result
