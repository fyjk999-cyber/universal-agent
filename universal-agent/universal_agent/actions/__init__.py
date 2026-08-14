"""actions package — Action Gateway family."""
from __future__ import annotations

from ..core.contracts import ActionIntent, ActionLevel, ActionPlan, ActionResult
from .approval import ApprovalInbox
from .compensation import CompensationManager, CompensationResult, CompensationStep
from .gateway import (
    ActionGateway,
    ActionPreparer,
    ControlledExecutor,
    ExecOutcome,
    PrepareOutcome,
)
from .idempotency import DuplicateRequest, IdempotencyStore
from .policy import KillSwitch, KillSwitchTripped, PolicyEngine, PolicyRule, PolicyViolation
from .slippage import SlippageGuard, SlippageResult

__all__ = [
    "ActionGateway",
    "ActionIntent",
    "ActionLevel",
    "ActionPlan",
    "ActionPreparer",
    "CompensationManager",
    "CompensationResult",
    "CompensationStep",
    "ControlledExecutor",
    "ExecOutcome",
    "KillSwitch",
    "KillSwitchTripped",
    "PolicyEngine",
    "PolicyRule",
    "PolicyViolation",
    "ActionResult",
    "ApprovalInbox",
    "DuplicateRequest",
    "IdempotencyStore",
    "PrepareOutcome",
    "SlippageGuard",
    "SlippageResult",
]
