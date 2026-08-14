"""core.change_detection package."""
from __future__ import annotations

from .detector import ChangeResult, detect_material_change

__all__ = ["ChangeResult", "detect_material_change"]
