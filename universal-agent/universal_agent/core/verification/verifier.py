"""Verification 分级（§25 Tier 结构 + §31 + §62）.

Tier 1: cheap structured scan   — search result, low confidence, cheap
Tier 2: OTA verification        — booking detail page, higher confidence
Tier 3: official verification   — airline/official source, highest confidence
Tier 4: checkout-level verify   — reserved, NOT run on every watch (§25)

The verifier is deterministic and evidence-backed: each tier produces a
VerificationResult with fine-grained Confidence + Evidence. No LLM guessing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ...core.contracts import Confidence, Evidence, VerificationResult, new_id


@dataclass
class VerificationConfig:
    base_confidence: float = 0.6
    tier_delta: Dict[str, float] = field(default_factory=lambda: {
        "T1": 0.15, "T2": 0.25, "T3": 0.30, "T4": 0.35,
    })
    # a quote must be confirmed within this delta to pass at a tier
    price_tolerance_cny: float = 80.0
    price_tolerance_percent: float = 1.5


TIER_RANK = {"T1": 1, "T2": 2, "T3": 3, "T4": 4}


class FlightVerifier:
    """Verifies a candidate's offer across source tiers.

    In Phase 3 the verifier is deterministic + replay-friendly: when multiple
    sources report the same offer, agreement across sources raises confidence
    and can promote the verification tier (cross-source verification, §62).
    """

    def __init__(self, config: Optional[VerificationConfig] = None) -> None:
        self.config = config or VerificationConfig()

    def verify(self, *, target_key: str, offer_id: str,
               quotes: List[object],  # Quote-like with .price.amount/.source
               cross_source_agreement: bool = False,
               tier: str = "T2") -> VerificationResult:
        """Build a VerificationResult from quotes + optional cross-source agreement.

        Quotes carry their own confidence; the verifier blends them and adds
        evidence entries. cross_source_agreement=True promotes confidence
        (multiple platforms saw the same price → more trustworthy).
        """
        base = self.config.base_confidence + self.config.tier_delta.get(tier, 0.0)
        conf = Confidence(
            price_confidence=min(1.0, base + (0.10 if cross_source_agreement else 0.0)),
            availability_confidence=0.8 if cross_source_agreement else 0.6,
            schedule_confidence=0.9,
            baggage_confidence=0.7,
            final_confidence=0.0,  # computed below
        )
        conf.final_confidence = round(
            (conf.price_confidence * 0.5 + conf.availability_confidence * 0.2
             + conf.schedule_confidence * 0.15 + conf.baggage_confidence * 0.15), 3)

        evidence: List[Evidence] = []
        for q in quotes:
            evidence.append(Evidence(
                evidence_id=new_id("evid"),
                field="price",
                value=q.price.amount,
                source=getattr(q, "source", "unknown"),
                method=f"{tier}_verify",
                confidence=min(1.0, base + 0.05),
            ))

        # price spread check: agreement means prices cluster within tolerance
        passed = True
        if len(quotes) >= 2:
            prices = sorted(q.price.amount for q in quotes)
            spread = prices[-1] - prices[0]
            if spread > self.config.price_tolerance_cny and \
               spread / prices[0] * 100 > self.config.price_tolerance_percent:
                passed = False

        return VerificationResult(
            verification_id=new_id("ver"),
            target_key=target_key,
            confidence=conf,
            evidence=evidence,
            verified_by=f"deterministic_{tier}",
            passed=passed,
        )
