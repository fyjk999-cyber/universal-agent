"""TaskSpec v1 / WatchTask v1 — the primary task contracts (§13, §14).

TaskSpec supports: oneshot | scheduled | watch | condition_watch | composite.
WatchTask adds explicit lifecycle state machine (§14) — never a plain boolean.
"""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from .base import utc_now


class TaskType(str, Enum):
    ONESHOT = "oneshot"
    SCHEDULED = "scheduled"
    WATCH = "watch"
    CONDITION_WATCH = "condition_watch"
    COMPOSITE = "composite"


class TaskDomain(str, Enum):
    TRAVEL = "travel"
    FLIGHT = "flight"
    HOTEL = "hotel"
    RAILWAY = "railway"
    ECOMMERCE = "ecommerce"
    JOBS = "jobs"
    FOOD = "food"


class WatchState(str, Enum):
    """WatchTask explicit state machine (§14).

    Main line: DRAFT → ACTIVE → WATCHING → MATCH_FOUND → NOTIFIED
                → ACTION_PENDING → FULFILLED
    Auxiliary: PAUSED / CANCELLED / EXPIRED / FAILED
    """

    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    WATCHING = "WATCHING"
    MATCH_FOUND = "MATCH_FOUND"
    NOTIFIED = "NOTIFIED"
    ACTION_PENDING = "ACTION_PENDING"
    FULFILLED = "FULFILLED"
    PAUSED = "PAUSED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"


#: states that count as "still alive" (kept outside the Enum so it is not a member)
ALIVE_STATES: frozenset = frozenset({
    WatchState.ACTIVE, WatchState.WATCHING, WatchState.MATCH_FOUND,
    WatchState.NOTIFIED, WatchState.ACTION_PENDING, WatchState.PAUSED,
})


class Lifecycle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    starts_at: Optional[date] = None
    expires_at: Optional[date] = None


class Schedule(BaseModel):
    """Baseline schedule (§15). Adaptive flag reserved for Phase B+."""

    model_config = ConfigDict(extra="forbid")

    timezone: str = "Asia/Shanghai"
    baseline: List[str] = Field(default_factory=list)  # ["09:00","15:00","21:00"]
    adaptive: bool = False


class SearchSpace(BaseModel):
    """Domain-specific search space. Kept generic at contract level.

    Flight example (§13):
      origin: [HGH, PVG, SHA]
      destination: [ZQN]
      departure: {start, end}
      nights: {min, preferred, max}
    """

    model_config = ConfigDict(extra="allow")

    origin: List[str] = Field(default_factory=list)
    destination: List[str] = Field(default_factory=list)
    departure: Optional[Dict[str, Any]] = None  # {"start": date, "end": date}
    nights: Optional[Dict[str, int]] = None  # {"min": 6, "preferred": 7, "max": 8}
    extra: Dict[str, Any] = Field(default_factory=dict)


class TriggerRule(BaseModel):
    """Notification trigger conditions (§33)."""

    model_config = ConfigDict(extra="forbid")

    opportunity_score_gte: Optional[float] = None
    price_drop_cny_gte: Optional[float] = None
    price_drop_percent_gte: Optional[float] = None
    historical_low: Optional[bool] = None


class TaskSpec(BaseModel):
    """TaskSpec v1 — the frozen task contract (§13)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    type: TaskType
    domain: TaskDomain
    schema_version: str = "1.0"

    lifecycle: Lifecycle = Field(default_factory=Lifecycle)
    schedule: Schedule = Field(default_factory=Schedule)
    search_space: SearchSpace = Field(default_factory=SearchSpace)
    notify_if: TriggerRule = Field(default_factory=TriggerRule)
    meta: Dict[str, Any] = Field(default_factory=dict)


class WatchTask(TaskSpec):
    """WatchTask v1 = TaskSpec + explicit lifecycle state + runtime fields."""

    model_config = ConfigDict(extra="forbid")

    state: WatchState = WatchState.DRAFT
    version: int = 1  # incremented on each persisted state transition
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    last_scan_at: Optional[datetime] = None
    next_scan_at: Optional[datetime] = None
    scan_count: int = 0
    notified_fingerprints: List[str] = Field(default_factory=list)  # §34 dedup
    history: List[Dict[str, Any]] = Field(default_factory=list)  # compact state log
