"""Score / Opportunity / Trigger contracts (§32, §33)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field

from .base import utc_now


class ScoreResult(BaseModel):
    """Deterministic composite score result."""

    model_config = ConfigDict(extra="forbid")

    score_id: str
    target_key: str  # candidate_id / offer_id / bundle_id
    score_type: str = "candidate"
    components: Dict[str, float] = Field(default_factory=dict)
    total_score: float = Field(default=0.0, ge=0.0, le=100.0)
    scored_at: datetime = Field(default_factory=utc_now)


class OpportunityScore(ScoreResult):
    """Opportunity Engine output (§32) — deterministic, evidence-based."""

    model_config = ConfigDict(extra="forbid")

    historical_low: bool = False
    absolute_drop_cny: float = 0.0
    percent_drop: float = 0.0
    price_percentile: float = Field(default=100.0, ge=0.0, le=100.0)
    candidate_score: float = Field(default=0.0, ge=0.0, le=100.0)
    offer_trust: float = Field(default=0.0, ge=0.0, le=1.0)
    verification_confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class TriggerEvent(BaseModel):
    """Result of evaluating notify_if rules (§33)."""

    model_config = ConfigDict(extra="forbid")

    trigger_id: str
    task_id: str
    target_key: Optional[str] = None
    rule: Dict[str, Any] = Field(default_factory=dict)
    matched: bool = False
    severity: str = "info"  # attention | important
    reason: str = ""
    generated_at: datetime = Field(default_factory=utc_now)
