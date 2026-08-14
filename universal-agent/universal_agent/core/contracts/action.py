"""ActionPlan / ActionIntent / ActionResult — decision/execution separation (§36)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from .base import ActionLevel, Reversibility, utc_now


class ActionIntent(BaseModel):
    """One intended side-effecting action. Always carries idempotency_key (§38)."""

    model_config = ConfigDict(extra="forbid")

    intent_id: str
    action: str  # prepare_order | submit_application | ...
    target_key: Optional[str] = None
    params: Dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str
    level: ActionLevel = ActionLevel.L1_RECOMMEND
    reversibility: Reversibility = Reversibility.FULL
    max_slippage_cny: Optional[float] = None  # §39
    max_slippage_percent: Optional[float] = None

    # ---- P0.3: 批准快照（approved vs actual 滑移校验）----
    approved_quote_id: Optional[str] = None
    approved_offer_id: Optional[str] = None
    approved_price_cny: Optional[float] = None
    approved_at: Optional[datetime] = None
    approval_expires_at: Optional[datetime] = None
    offer_version: Optional[str] = None
    candidate_version: Optional[str] = None


class ActionPlan(BaseModel):
    """A decision's plan. Domains build it; nothing executes it directly (§36)."""

    model_config = ConfigDict(extra="forbid")

    plan_id: str
    task_id: str
    target_key: Optional[str] = None
    intents: List[ActionIntent] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    status: str = "PLANNED"  # PLANNED | APPROVED | REJECTED | EXECUTING | DONE | FAILED


class ActionResult(BaseModel):
    """Outcome of executing one ActionIntent via the Action Gateway."""

    model_config = ConfigDict(extra="forbid")

    intent_id: str
    plan_id: str
    status: str = "EXECUTED"  # EXECUTED | ABORTED | FAILED | COMPENSATED
    detail: Dict[str, Any] = Field(default_factory=dict)
    executed_at: datetime = Field(default_factory=utc_now)
    audit_ref: Optional[str] = None
