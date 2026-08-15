"""MemoryRecord contract (§17)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from .base import Scope, utc_now


class MemoryRecord(BaseModel):
    """One memory record. Always tagged with scope + domain + task when relevant."""

    model_config = ConfigDict(extra="forbid")

    record_id: str
    scope: Scope
    domain: Optional[str] = None
    task_id: Optional[str] = None
    key: str
    value: Any
    kind: str = "fact"  # fact | preference | decision | answer | policy | ...
    version: int = 1
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    source: str = "system"
    expires_at: Optional[datetime] = None
    # P3: 用户/档案隔离 + 置信度
    user_id: Optional[str] = None
    profile_id: Optional[str] = None
    confidence: Optional[float] = None


class MemoryQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: Optional[Scope] = None
    domain: Optional[str] = None
    task_id: Optional[str] = None
    key: Optional[str] = None
    kind: Optional[str] = None
    limit: int = 50
