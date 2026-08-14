"""Contract tests for every frozen Phase 0 data contract (§45)."""
from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from universal_agent.core.contracts import (
    ActionIntent,
    ActionLevel,
    ActionPlan,
    Candidate,
    CandidateEnvelope,
    Confidence,
    Evidence,
    MemoryRecord,
    Money,
    Observation,
    Offer,
    OpportunityScore,
    Quote,
    Reversibility,
    Scope,
    SkillManifest,
    TaskDomain,
    TaskSpec,
    TaskType,
    TriggerEvent,
    VerificationResult,
    WatchState,
    WatchTask,
)


# ---------------------------------------------------------------- TaskSpec
class TestTaskSpec:
    def test_queenstown_spec(self, queenstown_spec):
        assert queenstown_spec.id == "queenstown-travel-watch"
        assert queenstown_spec.type == TaskType.WATCH
        assert queenstown_spec.domain == TaskDomain.TRAVEL
        assert queenstown_spec.schema_version == "1.0"
        assert queenstown_spec.search_space.origin == ["HGH", "PVG", "SHA"]
        assert queenstown_spec.search_space.destination == ["ZQN"]

    def test_supports_all_five_types(self):
        for t in TaskType:
            spec = TaskSpec(id=f"t-{t.value}", type=t, domain="flight")
            assert spec.type == t

    def test_extra_fields_rejected(self):
        with pytest.raises(ValidationError):
            TaskSpec(id="x", type="watch", domain="flight", bogus=1)

    def test_json_roundtrip(self, queenstown_spec):
        raw = json.dumps(queenstown_spec.model_dump(mode="json"))
        again = TaskSpec.model_validate_json(raw)
        assert again == queenstown_spec


# ---------------------------------------------------------------- WatchTask
class TestWatchTask:
    def test_default_state_is_draft(self, queenstown_watch):
        assert queenstown_watch.state == WatchState.DRAFT
        assert queenstown_watch.version == 1

    def test_no_plain_boolean_lifecycle(self):
        # RULE §14: forbid is_active-style bool
        assert "is_active" not in WatchTask.model_fields
        assert "state" in WatchTask.model_fields

    def test_explicit_state_machine_values(self):
        expected = {
            "DRAFT", "ACTIVE", "WATCHING", "MATCH_FOUND", "NOTIFIED",
            "ACTION_PENDING", "FULFILLED", "PAUSED", "CANCELLED", "EXPIRED", "FAILED",
        }
        assert {s.value for s in WatchState} == expected

    def test_serialization_roundtrip(self, queenstown_watch):
        raw = json.dumps(queenstown_watch.model_dump(mode="json"))
        again = WatchTask.model_validate_json(raw)
        assert again.id == queenstown_watch.id
        assert again.state == WatchState.DRAFT


# ---------------------------------------------------------------- Candidate
class TestCandidateOfferQuote:
    def test_candidate_offer_quote_separated(self):
        cand = Candidate(candidate_id="c1", domain="flight", task_id="t1")
        offer = Offer(offer_id="o1", candidate_id="c1", marketplace_id="ctrip")
        quote = Quote(quote_id="q1", offer_id="o1", price=Money(amount=4380.0))
        assert cand.candidate_id == "c1"
        assert offer.candidate_id == "c1"
        assert quote.offer_id == "o1"
        assert quote.price.cents == 438000

    def test_candidate_envelope(self):
        cand = Candidate(candidate_id="c1", domain="flight", task_id="t1")
        env = CandidateEnvelope(candidate=cand, source="ctrip")
        assert env.candidate.candidate_id == "c1"

    def test_entity_resolution_key_supported(self):
        cand = Candidate(candidate_id="c1", domain="flight", task_id="t1",
                         entity_key="2026-08-30|PVG|ZQN|MU779")
        assert cand.entity_key is not None


# ---------------------------------------------------------------- Facts
class TestFactsLayer:
    def test_observation_is_fact(self):
        obs = Observation(observation_id="o1", task_id="t1", domain="flight",
                          kind="price", value=4380, unit="CNY")
        assert obs.kind == "price"
        assert obs.value == 4380

    def test_evidence_fields(self):
        ev = Evidence(evidence_id="e1", field="price", value=4380,
                      source="ctrip", method="booking_detail", confidence=0.91)
        assert ev.source == "ctrip"
        assert ev.confidence == 0.91

    def test_verification_fine_grained_confidence(self):
        conf = Confidence(price_confidence=0.9, availability_confidence=0.8,
                          schedule_confidence=0.95, baggage_confidence=0.7,
                          final_confidence=0.88)
        vr = VerificationResult(verification_id="v1", target_key="c1",
                                confidence=conf, passed=True)
        assert vr.confidence.final_confidence == 0.88
        assert vr.passed is True

    def test_confidence_bounds_enforced(self):
        with pytest.raises(ValidationError):
            Confidence(final_confidence=1.5)


# ---------------------------------------------------------------- Scoring
class TestScoring:
    def test_opportunity_score_deterministic_fields(self):
        os = OpportunityScore(
            score_id="s1", target_key="c1",
            total_score=92.0, historical_low=True,
            absolute_drop_cny=520.0, percent_drop=11.5,
            price_percentile=12.0, candidate_score=88.0,
            offer_trust=0.9, verification_confidence=0.85,
        )
        assert os.historical_low is True
        assert os.total_score == 92.0

    def test_trigger_event(self):
        te = TriggerEvent(trigger_id="tr1", task_id="t1", matched=True,
                          severity="important", reason="historical low")
        assert te.matched is True


# ---------------------------------------------------------------- Action
class TestAction:
    def test_action_intent_requires_idempotency_key(self):
        with pytest.raises(ValidationError):
            ActionIntent(intent_id="i1", action="prepare_order")

    def test_action_plan_is_plan_only(self):
        intent = ActionIntent(intent_id="i1", action="prepare_order",
                              idempotency_key="k1", level=ActionLevel.L2_PREPARE,
                              reversibility=Reversibility.PARTIAL)
        plan = ActionPlan(plan_id="p1", task_id="t1", intents=[intent])
        assert plan.status == "PLANNED"
        # §36: plan has no execute() method
        assert not hasattr(plan, "execute")


# ---------------------------------------------------------------- Memory
class TestMemoryContract:
    def test_scope_required(self):
        rec = MemoryRecord(record_id="m1", scope=Scope.GLOBAL, key="avoid_self_transfer",
                           value=True, domain="flight")
        assert rec.scope == Scope.GLOBAL
        assert rec.kind == "fact"

    def test_domain_scope_example(self):
        rec = MemoryRecord(record_id="m1", scope=Scope.DOMAIN, domain="flight",
                           key="avoid_self_transfer", value=True)
        assert rec.scope == Scope.DOMAIN

    def test_task_scope_example(self):
        rec = MemoryRecord(record_id="m1", scope=Scope.TASK, task_id="t1",
                           key="allow_two_stops", value=True)
        assert rec.task_id == "t1"


# ---------------------------------------------------------------- Registry
class TestRegistryContracts:
    def test_skill_manifest_declares_capabilities(self):
        sm = SkillManifest(skill_id="ctrip.flight", version="0.1.0",
                           domains=["flight"],
                           capabilities={"search": True, "detail": True,
                                         "availability": True, "price_verify": True,
                                         "prepare_order": False, "execute_order": False},
                           transport=["browser"], risk={"execution": "none"})
        assert sm.capabilities["execute_order"] is False

    def test_marketplace_manifest(self):
        mm = {"id": "ctrip", "domains": ["flight", "hotel", "railway"],
              "capabilities": {"search": True, "detail": True},
              "trust": {"default_score": 0.9}}
        from universal_agent.core.contracts import MarketplaceManifest
        m = MarketplaceManifest(**mm)
        assert m.trust["default_score"] == 0.9
