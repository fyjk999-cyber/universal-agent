"""jobs domain package."""
from __future__ import annotations

from .action import build_application_plan, store_answer_memory, store_application_draft
from .knowledge import DEFAULT_WANTED_SKILLS, entity_key, match_ratio, salary_midpoint
from .normalize import normalize_job
from .scoring import score_job

__all__ = [
    "DEFAULT_WANTED_SKILLS",
    "build_application_plan",
    "entity_key",
    "match_ratio",
    "normalize_job",
    "salary_midpoint",
    "score_job",
    "store_answer_memory",
    "store_application_draft",
]
