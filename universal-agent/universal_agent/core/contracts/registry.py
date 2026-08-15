"""SkillManifest / MarketplaceManifest — registry contracts (§22, §23)."""
from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class SkillManifest(BaseModel):
    """Every skill MUST declare capabilities explicitly (§23)."""

    model_config = ConfigDict(extra="forbid")

    skill_id: str
    version: str = "0.1.0"
    domains: List[str] = Field(default_factory=list)
    capabilities: Dict[str, bool] = Field(default_factory=dict)
    transport: List[str] = Field(default_factory=list)  # api | http | browser | mobile
    risk: Dict[str, str] = Field(default_factory=dict)  # {"execution": "none"}
    description: str = ""
    # P5: CapabilityResolver 评分依据
    health: str = "UNKNOWN"     # HEALTHY | DEGRADED | UNAVAILABLE | AUTH_REQUIRED | RATE_LIMITED
    cost: float = 0.5           # 0..1（越高越贵）
    trust: float = 0.5          # 0..1（越高越可信）


class MarketplaceManifest(BaseModel):
    """Marketplace declaration (§22)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    domains: List[str] = Field(default_factory=list)
    capabilities: Dict[str, bool] = Field(default_factory=dict)
    trust: Dict[str, float] = Field(default_factory=dict)  # {"default_score": 0.9}
    health: str = "UNKNOWN"  # HEALTHY | DEGRADED | UNAVAILABLE | AUTH_REQUIRED
    endpoints: Optional[Dict[str, str]] = None
