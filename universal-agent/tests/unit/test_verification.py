"""Verification 分级测试（§25/§31/§62）。"""
from __future__ import annotations

from universal_agent.core.contracts import Money, Quote
from universal_agent.core.verification import FlightVerifier, VerificationConfig


def _q(amount: float, src: str) -> Quote:
    return Quote(quote_id=f"q-{src}-{amount}", offer_id="o1",
                 price=Money(amount=amount), source=src)


class TestFlightVerifier:
    def test_single_quote_t2(self):
        v = FlightVerifier()
        r = v.verify(target_key="k1", offer_id="o1", quotes=[_q(4380, "ctrip")],
                     cross_source_agreement=False, tier="T2")
        assert r.passed is True
        assert r.confidence.final_confidence > 0.7
        assert r.verified_by == "deterministic_T2"
        assert r.evidence[0].source == "ctrip"

    def test_cross_source_agreement_boosts_confidence(self):
        v = FlightVerifier()
        single = v.verify(target_key="k1", offer_id="o1", quotes=[_q(4380, "ctrip")],
                          cross_source_agreement=False, tier="T2")
        cross = v.verify(target_key="k1", offer_id="o1",
                         quotes=[_q(4380, "ctrip"), _q(4390, "fliggy")],
                         cross_source_agreement=True, tier="T2")
        assert cross.confidence.price_confidence > single.confidence.price_confidence

    def test_price_spread_beyond_tolerance_fails(self):
        v = FlightVerifier(config=VerificationConfig(price_tolerance_cny=80,
                                                     price_tolerance_percent=1.5))
        r = v.verify(target_key="k1", offer_id="o1",
                     quotes=[_q(4380, "ctrip"), _q(4900, "fliggy")],
                     cross_source_agreement=True, tier="T2")
        assert r.passed is False  # ¥520 spread exceeds tolerance

    def test_higher_tier_higher_confidence(self):
        v = FlightVerifier()
        t1 = v.verify(target_key="k1", offer_id="o1", quotes=[_q(4380, "ctrip")], tier="T1")
        t3 = v.verify(target_key="k1", offer_id="o1", quotes=[_q(4380, "ctrip")], tier="T3")
        assert t3.confidence.price_confidence > t1.confidence.price_confidence

    def test_fine_grained_confidence_fields(self):
        v = FlightVerifier()
        r = v.verify(target_key="k1", offer_id="o1", quotes=[_q(4380, "ctrip")], tier="T2")
        conf = r.confidence
        for field in ("price_confidence", "availability_confidence",
                      "schedule_confidence", "baggage_confidence", "final_confidence"):
            assert 0.0 <= getattr(conf, field) <= 1.0
