"""EventEnvelope — the universal event contract (§5)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field

from ..core.contracts import new_id, utc_now
from .types import EventType


class EventEnvelope(BaseModel):
    """Every event on the bus uses this envelope."""

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(default_factory=lambda: new_id("evt"))
    event_type: EventType
    schema_version: str = "1.0"
    trace_id: str
    task_id: Optional[str] = None
    run_id: Optional[str] = None            # P2: 关联 ScanRun
    correlation_id: Optional[str] = None    # P2: 跨事件流程关联
    causation_id: Optional[str] = None      # P2: 直接前因事件
    source: str = "universal-agent"
    created_at: datetime = Field(default_factory=utc_now)
    payload: Dict[str, Any] = Field(default_factory=dict)
