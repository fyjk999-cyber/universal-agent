"""Change detection + Opportunity Engine + Trigger tests (§32, §33, §71)."""
from __future__ import annotations

from universal_agent.core.change_detection import detect_material_change
from universal_agent.core.contracts import Money, OpportunityScore, Quote, TaskSpec
from universal_agent.core.opportunity import OpportunityInput, compute_opportunity
from universal_agent.coordinator.trigger_engine import evaluate_triggers


def _quote(amount: float) -> Quote:
    return Quote(quote_id=f"q-{amount}", offer_id="o1", price=Money(amount=amount))


class TestChangeDetection:
    def test_no_previous_is_change(self):
        r = detect_material_change(_quote(4380), None)
        assert r.changed is True

    def test_same_price_not_material(self):
        r = detect_material_change(_quote(4380), _quote(4380))
        assert r.changed is False  # §71: no material change → no re-notify

    def test_drop_beyond_threshold_is_material(self):
        r = detect_material_change(_quote(3980), _quote(4380))
        assert r.changed is True
        assert r.delta_cny == -400
        assert r.delta_percent < 0


class TestOpportunity:
    def test_historical_low_detected(self):
        history = [_quote(4800), _quote(4500), _quote(4300)]
        opp = compute_opportunity(OpportunityInput(
            quotes=history, current_price=4300))
        assert opp.historical_low is True
        assert opp.total_score >= 90

    def test_not_historical_low(self):
        history = [_quote(4300), _quote(4500)]
        opp = compute_opportunity(OpportunityInput(
            quotes=history, current_price=4700))
        assert opp.historical_low is False
        assert opp.absolute_drop_cny == 0.0

    def test_percentile_lower_is_cheaper(self):
        hist = [_quote(4000), _quote(4500), _quote(5000), _quote(5500)]
        cheap = compute_opportunity(OpportunityInput(quotes=hist, current_price=4100))
        expensive = compute_opportunity(OpportunityInput(quotes=hist, current_price=5400))
        assert cheap.price_percentile < expensive.price_percentile


class TestTriggerEngine:
    def test_important_trigger_on_historical_low(self):
        task = TaskSpec(id="t1", type="watch", domain="flight",
                        notify_if={"historical_low": True,
                                   "opportunity_score_gte": 90})
        opp = OpportunityScore(score_id="s1", target_key="o1", total_score=95,
                               historical_low=True)
        events = evaluate_triggers(task, opp)
        assert len(events) == 1
        assert events[0].matched is True
        assert events[0].severity == "important"
        assert "historical_low" in events[0].reason

    def test_no_trigger_when_no_match(self):
        task = TaskSpec(id="t1", type="watch", domain="flight",
                        notify_if={"opportunity_score_gte": 90})
        opp = OpportunityScore(score_id="s1", target_key="o1", total_score=50)
        assert evaluate_triggers(task, opp) == []

    def test_attention_severity_for_small_drop(self):
        task = TaskSpec(id="t1", type="watch", domain="flight",
                        notify_if={"price_drop_cny_gte": 300})
        opp = OpportunityScore(score_id="s1", target_key="o1", total_score=70,
                               absolute_drop_cny=320)
        events = evaluate_triggers(task, opp)
        assert events and events[0].severity == "attention"
