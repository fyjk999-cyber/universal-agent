"""Core data contracts — public API surface (§12)."""
from __future__ import annotations

from .action import ActionIntent, ActionPlan, ActionResult
from .bundle import BundleCandidate
from .base import (
    ActionLevel,
    Confidence,
    Money,
    Reversibility,
    Scope,
    new_id,
    utc_now,
)
from .candidate import Candidate, CandidateEnvelope, Offer, Quote
from .memory import MemoryQuery, MemoryRecord
from .observation import Evidence, Observation, VerificationResult
from .raw import (DataCompleteness, RankEligibility, RawHotel, RawJob,
                      RawLeg, RawListing, RawSegment, field_completeness_score,
                      rank_eligibility)
from .scanrun import ExecutionState, ScanRun, ScanRunStatus, is_retryable
from .registry import MarketplaceManifest, SkillManifest
from .scoring import OpportunityScore, ScoreResult, TriggerEvent
from .task import (
    ALIVE_STATES,
    Lifecycle,
    Schedule,
    SearchSpace,
    TaskDomain,
    TaskSpec,
    TaskType,
    TriggerRule,
    WatchState,
    WatchTask,
)

__all__ = [
    "ALIVE_STATES",
    "ActionIntent",
    "BundleCandidate",
    "ActionLevel",
    "ActionPlan",
    "ActionResult",
    "Candidate",
    "CandidateEnvelope",
    "Confidence",
    "Evidence",
    "Lifecycle",
    "MarketplaceManifest",
    "MemoryQuery",
    "MemoryRecord",
    "Money",
    "Observation",
    "Offer",
    "OpportunityScore",
    "Quote",
    "DataCompleteness",
    "RankEligibility",
    "rank_eligibility",
    "RawHotel",
    "field_completeness_score",
    "ExecutionState",
    "ScanRun",
    "ScanRunStatus",
    "is_retryable",
    "RawJob",
    "RawLeg",
    "RawListing",
    "RawSegment",
    "Reversibility",
    "Schedule",
    "Scope",
    "ScoreResult",
    "SearchSpace",
    "SkillManifest",
    "TaskDomain",
    "TaskSpec",
    "TaskType",
    "TriggerEvent",
    "TriggerRule",
    "VerificationResult",
    "WatchState",
    "WatchTask",
    "new_id",
    "utc_now",
]
