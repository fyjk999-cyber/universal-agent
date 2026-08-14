"""Flight domain package."""
from __future__ import annotations

from .knowledge import candidate_attributes, entity_key, flight_numbers
from .normalize import normalize_listing, to_envelope

__all__ = [
    "candidate_attributes",
    "entity_key",
    "flight_numbers",
    "normalize_listing",
    "to_envelope",
]
