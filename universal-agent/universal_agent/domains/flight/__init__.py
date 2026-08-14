"""Flight domain package."""
from __future__ import annotations

from .knowledge import (
    ResolutionConfidence,
    ResolutionResult,
    candidate_attributes,
    entity_key,
    flight_numbers,
    resolve,
    strong_entity_key,
    weak_entity_key,
)
from .normalize import normalize_listing, to_envelope

__all__ = [
    "ResolutionConfidence",
    "ResolutionResult",
    "candidate_attributes",
    "entity_key",
    "flight_numbers",
    "normalize_listing",
    "resolve",
    "strong_entity_key",
    "to_envelope",
    "weak_entity_key",
]
