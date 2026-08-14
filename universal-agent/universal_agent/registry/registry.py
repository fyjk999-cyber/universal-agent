"""Skill + Marketplace Registry with capability enforcement (§22, §23, §43).

Registry is the enforcement point: if a SkillManifest declares
execute_order=false, the registry refuses any request for that capability —
even if the underlying code tries to call it.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from ..core.contracts import MarketplaceManifest, SkillManifest


class CapabilityDenied(RuntimeError):
    pass


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: Dict[str, SkillManifest] = {}
        self._marketplaces: Dict[str, MarketplaceManifest] = {}

    # ---- skills ----
    def register_skill(self, manifest: SkillManifest) -> None:
        self._skills[manifest.skill_id] = manifest

    def get_skill(self, skill_id: str) -> Optional[SkillManifest]:
        return self._skills.get(skill_id)

    def list_skills(self, domain: Optional[str] = None) -> List[SkillManifest]:
        if domain is None:
            return list(self._skills.values())
        return [s for s in self._skills.values() if domain in s.domains]

    def assert_capability(self, skill_id: str, capability: str) -> None:
        """§43: reject capability the manifest does not grant."""
        skill = self._skills.get(skill_id)
        if skill is None:
            raise CapabilityDenied(f"unknown skill: {skill_id}")
        if not skill.capabilities.get(capability, False):
            raise CapabilityDenied(
                f"skill {skill_id} does not grant capability {capability}")

    # ---- marketplaces ----
    def register_marketplace(self, manifest: MarketplaceManifest) -> None:
        self._marketplaces[manifest.id] = manifest

    def get_marketplace(self, marketplace_id: str) -> Optional[MarketplaceManifest]:
        return self._marketplaces.get(marketplace_id)

    def list_marketplaces(self, domain: Optional[str] = None,
                          healthy_only: bool = False) -> List[MarketplaceManifest]:
        out = list(self._marketplaces.values())
        if domain is not None:
            out = [m for m in out if domain in m.domains]
        if healthy_only:
            out = [m for m in out if m.health == "HEALTHY"]
        return out

    def set_marketplace_health(self, marketplace_id: str, health: str) -> None:
        if marketplace_id in self._marketplaces:
            self._marketplaces[marketplace_id].health = health
