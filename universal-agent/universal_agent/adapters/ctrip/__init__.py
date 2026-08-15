"""Ctrip HTTP Flight Skill（FR-074 第二 Flight Live Source，CH4-4.2）。"""
from __future__ import annotations

from .adapter import CtripFlightSkill, SkillUnavailable, ctrip_marketplace_manifest, ctrip_skill_manifest

__all__ = ["CtripFlightSkill", "SkillUnavailable", "ctrip_marketplace_manifest",
           "ctrip_skill_manifest"]
