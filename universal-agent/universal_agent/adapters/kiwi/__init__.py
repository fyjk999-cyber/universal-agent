"""Kiwi Tequila Flight Skill（真实 Flight 价格 API）。"""
from __future__ import annotations

from .adapter import (
    KiwiTequilaFlightSkill,
    kiwi_marketplace_manifest,
    kiwi_skill_manifest,
)

__all__ = ["KiwiTequilaFlightSkill", "kiwi_marketplace_manifest", "kiwi_skill_manifest"]
