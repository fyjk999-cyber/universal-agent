"""BundleCandidate — Flight + Hotel composite (§27)."""
from __future__ import annotations

from typing import Dict, Optional

from pydantic import BaseModel, ConfigDict, Field

from .base import utc_now


class BundleCandidate(BaseModel):
    """Flight + Hotel bundle with component costs and composite score.

    Future extension: Flight + Hotel + Rail + Transfer (§27).
    """

    model_config = ConfigDict(extra="forbid")

    bundle_id: str
    task_id: str
    components: Dict[str, str] = Field(default_factory=dict)  # {"flight": cand_id, "hotel": cand_id}
    cost: Dict[str, float] = Field(default_factory=dict)  # {"flight": ..., "hotel": ..., "total": ...}
    score: float = Field(default=0.0, ge=0.0, le=100.0)
    notes: list[str] = Field(default_factory=list)
