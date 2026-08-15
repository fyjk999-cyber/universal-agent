"""P11 — Opportunity Engine：availability + momentum/volatility 预趋势。

规则层（现已有）：historical low / absolute drop / percentage drop /
percentile / candidate score / offer trust / verification confidence。

P11 补：
1. availability（库存风险）影响机会分
2. momentum（价格趋势方向）
3. volatility（波动率）—— 只影响提示，不作为事实
4. 预测不是事实：trend 字段标注为 estimate
"""
from __future__ import annotations

from pathlib import Path

import pytest

from universal_agent.core.contracts import Money, OpportunityScore, Quote


def _quote(offer_id: str, amount: float) -> Quote:
    return Quote(
        quote_id=f"q-{offer_id}-{amount}", offer_id=offer_id,
        price=Money(amount=amount, currency="CNY"), method="search",
        confidence=0.9, source="test",
    )


def test_opportunity_historical_low_boost() -> None:
    from universal_agent.core.opportunity import OpportunityInput, compute_opportunity
    quotes = [_quote("o1", 4000), _quote("o1", 4200), _quote("o1", 4500)]
    low = compute_opportunity(OpportunityInput(quotes=quotes, current_price=4000,
                                               candidate_score=80, offer_trust=0.9,
                                               verification_confidence=0.9))
    not_low = compute_opportunity(OpportunityInput(quotes=quotes, current_price=4400,
                                                   candidate_score=80, offer_trust=0.9,
                                                   verification_confidence=0.9))
    assert low.historical_low is True
    assert low.total_score > not_low.total_score


def test_opportunity_availability_signal() -> None:
    """库存风险 → 机会分提升（规则层 availability 信号）。"""
    from universal_agent.core.opportunity import OpportunityInput, compute_opportunity
    quotes = [_quote("o1", 4000)]
    base = compute_opportunity(OpportunityInput(quotes=quotes, current_price=4000))
    risky = compute_opportunity(OpportunityInput(quotes=quotes, current_price=4000,
                                                 availability="LOW"))  # 库存少
    assert risky.total_score > base.total_score


def test_momentum_estimate_not_fact() -> None:
    """momentum/trend 是 estimate，不作为事实（不进入历史判定）。"""
    from universal_agent.core.opportunity import OpportunityInput, compute_opportunity
    quotes = [_quote("o1", 4000), _quote("o1", 4100), _quote("o1", 3900)]
    out = compute_opportunity(OpportunityInput(quotes=quotes, current_price=3900,
                                               trend={"momentum": "down", "volatility": 0.12}))
    # trend 字段存在且标注 estimate
    assert out.trend is not None
    assert out.trend.get("momentum") == "down"
    assert out.trend.get("is_estimate") is True
