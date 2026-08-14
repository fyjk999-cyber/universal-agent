"""Source Planner (§24, §25, §53) — answers "where to search?".

Query Planner says WHAT to search; Source Planner picks WHICH sources by
tiering + health. Tier 1 cheap structured scan first; checkout-level verify
(Tier 4) must never run on every watch cycle.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from ...core.contracts import MarketplaceManifest
from ...registry import SkillRegistry

#: capability → tier. Skills with search capability fall in Tier 1-3.
TIER_RANK = {"T1": 1, "T2": 2, "T3": 3, "T4": 4}


@dataclass
class SourcePlan:
    task_id: str
    sources: List[MarketplaceManifest] = field(default_factory=list)

    @property
    def tier_labels(self) -> List[str]:
        return [f"{m.id}@{m.health}" for m in self.sources]


def plan_sources(task_id: str, domain: str, registry: SkillRegistry,
                 max_sources: int = 6, include_unhealthy: bool = False) -> SourcePlan:
    marketplaces = registry.list_marketplaces(domain=domain, healthy_only=True)
    if include_unhealthy:
        marketplaces = registry.list_marketplaces(domain=domain)
    # sort by trust score desc (best sources first), cap
    def trust(m: MarketplaceManifest) -> float:
        return float(m.trust.get("default_score", 0.5))

    marketplaces.sort(key=trust, reverse=True)
    return SourcePlan(task_id=task_id, sources=marketplaces[:max_sources])
