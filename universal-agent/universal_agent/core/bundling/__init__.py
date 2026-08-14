"""core.bundling package."""
from __future__ import annotations

from .optimizer import (
    BundleComponent,
    BundleResult,
    best_bundle,
    build_bundles,
)

__all__ = ["BundleComponent", "BundleResult", "best_bundle", "build_bundles"]
