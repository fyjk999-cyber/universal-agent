"""actions.idempotency — idempotency_key store (§38)."""
from __future__ import annotations

from .store import DuplicateRequest, IdempotencyStore

__all__ = ["DuplicateRequest", "IdempotencyStore"]
