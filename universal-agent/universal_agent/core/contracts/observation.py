"""Observation / Evidence / VerificationResult — fact layer (§29, §30, §31).

Observations are facts, never directly modified by LLM.
Evidence ties a key fact to source/method/timestamp/confidence.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from .base import Confidence, utc_now


class Observation(BaseModel):
    """An immutable factual observation at a point in time."""

    model_config = ConfigDict(extra="forbid")

    observation_id: str
    task_id: str
    domain: str
    kind: str  # price | availability | schedule | baggage | ...
    target_key: Optional[str] = None  # candidate_id / offer_id
    value: Any
    unit: Optional[str] = None
    observed_at: datetime = Field(default_factory=utc_now)
    evidence_refs: List[str] = Field(default_factory=list)


class Evidence(BaseModel):
    """A single piece of evidence backing one key fact (§30)."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    field: str
    value: Any
    source: str
    method: str
    observed_at: datetime = Field(default_factory=utc_now)
    snapshot_reference: Optional[str] = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class VerificationResult(BaseModel):
    """Structured verification outcome with fine-grained confidence (§31)."""

    model_config = ConfigDict(extra="forbid")

    verification_id: str
    target_key: str  # candidate_id / offer_id
    confidence: Confidence = Field(default_factory=Confidence)
    evidence: List[Evidence] = Field(default_factory=list)
    verified_at: datetime = Field(default_factory=utc_now)
    verified_by: str = "deterministic"  # never "llm guess"
    passed: bool = False
