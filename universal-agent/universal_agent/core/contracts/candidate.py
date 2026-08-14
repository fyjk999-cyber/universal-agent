"""Candidate / Offer / Quote — strictly separated (§20)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from .base import Money, utc_now


class Candidate(BaseModel):
    """The real-world object a user might purchase.

    Flight example: MU779 + NZ621, PVG → AKL → ZQN.
    Entity Resolution (§21) merges same real object from multiple sources.
    """

    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    domain: str
    task_id: str
    # entity resolution key — same real object shares the same key
    entity_key: Optional[str] = None
    attributes: Dict[str, Any] = Field(default_factory=dict)
    source_ids: List[str] = Field(default_factory=list)
    first_seen_at: datetime = Field(default_factory=utc_now)
    last_seen_at: datetime = Field(default_factory=utc_now)
    is_verified: bool = False


class CandidateEnvelope(BaseModel):
    """Candidate + its observation context (never dump live runtime objects)."""

    model_config = ConfigDict(extra="forbid")

    candidate: Candidate
    observed_at: datetime = Field(default_factory=utc_now)
    source: str


class Offer(BaseModel):
    """A selling scheme from one platform (Trip Offer / Fliggy Offer / ...)."""

    model_config = ConfigDict(extra="forbid")

    offer_id: str
    candidate_id: str
    marketplace_id: str  # e.g. "ctrip"
    terms: Dict[str, Any] = Field(default_factory=dict)  # fare class, baggage, etc.
    url: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class Quote(BaseModel):
    """A price of an Offer at a moment in time."""

    model_config = ConfigDict(extra="forbid")

    quote_id: str
    offer_id: str
    price: Money
    observed_at: datetime = Field(default_factory=utc_now)
    method: str = "search"  # search | booking_detail | checkout_verify
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    snapshot_reference: Optional[str] = None
    source: str = "unknown"  # marketplace/source that produced this quote
