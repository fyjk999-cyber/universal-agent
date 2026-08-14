"""Job scoring — deterministic 0-100（RULE 7）.

Dimensions: 匹配度 match、薪资 salary（相对市场）、可信度（公司有参考号加分）。
"""
from __future__ import annotations

from typing import Dict

from ...core.contracts import RawJob
from .knowledge import match_ratio, salary_midpoint


def score_job(raw: RawJob, market_salary: float,
              wanted_skills=None) -> Dict[str, float]:
    """Return {'total': ..., 'components': {...}}."""
    match = match_ratio(raw, wanted_skills or [])
    match_score = match * 100.0

    mid = salary_midpoint(raw)
    if market_salary <= 0 or mid <= 0:
        salary_score = 50.0 if mid > 0 else 0.0
    else:
        ratio = mid / market_salary
        salary_score = 100.0 if ratio >= 1.2 else max(20.0, ratio / 1.2 * 100.0)

    trust_score = 100.0 if raw.job_reference else 60.0  # 有官方参考号更可信

    total = match_score * 0.5 + salary_score * 0.3 + trust_score * 0.2
    return {
        "total": round(total, 1),
        "components": {"match": round(match_score, 1),
                       "salary": round(salary_score, 1),
                       "trust": round(trust_score, 1)},
    }
