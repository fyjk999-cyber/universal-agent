"""adapters.official — Tier3 官方源验证骨架。"""
from __future__ import annotations

from .registry import NoOpOfficialVerifier, OfficialSourceRegistry, StubOfficialVerifier

__all__ = ["NoOpOfficialVerifier", "OfficialSourceRegistry", "StubOfficialVerifier"]
