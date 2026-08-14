"""Job domain knowledge (RULE 3 — domain knows jobs, not platforms).

Job Entity Resolution key (§21):
    company | title | location | job_reference
Two sources seeing the same real job must produce the same key.
"""
from __future__ import annotations

from typing import List

from ...core.contracts import RawJob


def entity_key(raw: RawJob) -> str:
    """Deterministic job entity key."""
    parts = [raw.company.strip().lower()]
    if raw.title:
        parts.append(raw.title.strip().lower())
    if raw.location:
        parts.append(raw.location.strip().lower())
    if raw.job_reference:
        parts.append(raw.job_reference.strip().lower())
    return "|".join(parts)


#: 匹配度参考技能关键词（可由偏好学习扩展，§55）
DEFAULT_WANTED_SKILLS = [
    "python", "sql", "machine learning", "deep learning", "nlp",
    "fastapi", "pytorch", "tensorflow", "data", "llm", "agent",
    "backend", "api", "分布式", "算法",
]


def match_ratio(raw: RawJob, wanted_skills: List[str]) -> float:
    """职位描述/技能 与期望技能的匹配度 0-1（纯规则，RULE 7）。"""
    if not wanted_skills:
        return 0.5
    text = f"{raw.title} {raw.description} {' '.join(raw.skills)}".lower()
    hits = sum(1 for s in wanted_skills if s.lower() in text)
    return min(1.0, hits / max(1, len(wanted_skills) * 0.5))


def salary_midpoint(raw: RawJob) -> float:
    """取薪资中位（无则 0）。"""
    lo = raw.salary_min_cny or 0
    hi = raw.salary_max_cny or lo
    return (lo + hi) / 2.0 if (lo or hi) else 0.0
