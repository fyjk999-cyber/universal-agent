"""adapters.skyscanner — real Skyscanner source (browser-rendered)."""
from __future__ import annotations

from .adapter import SkyscannerAdapter, SkyscannerConfig, SourceUnavailable
from .manifest import skyscanner_marketplace_manifest, skyscanner_skill_manifest

__all__ = [
    "SkyscannerAdapter",
    "SkyscannerConfig",
    "SourceUnavailable",
    "skyscanner_marketplace_manifest",
    "skyscanner_skill_manifest",
]
