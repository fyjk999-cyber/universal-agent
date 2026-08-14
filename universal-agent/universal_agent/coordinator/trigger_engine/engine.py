"""Trigger Engine (§33) — deterministic evaluation of notify_if rules.

Pure function: TaskSpec.notify_if + OpportunityScore → TriggerEvent.
Supports candidate / offer / bundle triggers (first phase: offer-level).
"""
from __future__ import annotations

from typing import List, Optional

from ...core.contracts import OpportunityScore, TaskSpec, TriggerEvent, new_id


def evaluate_triggers(task: TaskSpec, opportunity: Optional[OpportunityScore]) -> List[TriggerEvent]:
    if opportunity is None:
        return []
    rules = task.notify_if
    events: List[TriggerEvent] = []
    reasons: List[str] = []
    severity = "info"

    if rules.opportunity_score_gte is not None and opportunity.total_score >= rules.opportunity_score_gte:
        reasons.append(f"opportunity_score {opportunity.total_score} ≥ {rules.opportunity_score_gte}")
        severity = "important"
    if rules.historical_low and opportunity.historical_low:
        reasons.append("historical_low")
        severity = "important"
    if rules.price_drop_cny_gte is not None and opportunity.absolute_drop_cny >= rules.price_drop_cny_gte:
        reasons.append(f"price_drop ¥{opportunity.absolute_drop_cny:.0f} ≥ ¥{rules.price_drop_cny_gte}")
        severity = "important" if opportunity.absolute_drop_cny >= 500 else "attention"
    if rules.price_drop_percent_gte is not None and opportunity.percent_drop >= rules.price_drop_percent_gte:
        reasons.append(f"price_drop {opportunity.percent_drop:.1f}% ≥ {rules.price_drop_percent_gte}%")
        severity = "important"

    if reasons:
        events.append(TriggerEvent(
            trigger_id=new_id("trig"),
            task_id=task.id,
            target_key=opportunity.target_key,
            rule=rules.model_dump(),
            matched=True,
            severity=severity,
            reason="; ".join(reasons),
        ))
    return events
