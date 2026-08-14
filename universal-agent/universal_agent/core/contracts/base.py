"""Common base types shared by all Universal Agent contracts.

Everything in this package is a plain data contract (Pydantic v2 models).
No harness, host, or infrastructure dependency may appear here.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    """Generate a deterministic-looking unique id: <prefix>_<uuid8>."""
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class Scope(str, Enum):
    """Memory scope (RULE: all memory must be tagged with one of these)."""

    GLOBAL = "GLOBAL"
    DOMAIN = "DOMAIN"
    TASK = "TASK"
    SESSION = "SESSION"


class Reversibility(str, Enum):
    """Reversibility model for side effects (§40)."""

    FULL = "FULL"
    PARTIAL = "PARTIAL"
    TIME_LIMITED = "TIME_LIMITED"
    IRREVERSIBLE = "IRREVERSIBLE"


class ActionLevel(str, Enum):
    """Action Gateway levels (§35). V1 only opens L0/L1."""

    L0_SCAN = "L0_SCAN"
    L1_RECOMMEND = "L1_RECOMMEND"
    L2_PREPARE = "L2_PREPARE"
    L3_CONFIRM = "L3_CONFIRM"
    L4_EXECUTE = "L4_EXECUTE"


class Confidence(BaseModel):
    """Fine-grained verification confidence (§31) — never a single blurry number."""

    price_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    availability_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    schedule_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    baggage_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    final_confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class Timestamped(BaseModel):
    model_config = ConfigDict(extra="forbid")

    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class Money(BaseModel):
    """Amount in a currency; all numeric comparisons must use cents internally."""

    amount: float
    currency: str = "CNY"

    @property
    def cents(self) -> int:
        return round(self.amount * 100)
