"""Job normalizer — RawJob → Candidate + Offer + Quote + Evidence."""
from __future__ import annotations

from typing import Tuple

from ...core.contracts import (
    Candidate,
    Evidence,
    Money,
    Offer,
    Quote,
    RawJob,
    new_id,
)
from .knowledge import entity_key, match_ratio, salary_midpoint


def normalize_job(raw: RawJob, task_id: str,
                  wanted_skills=None) -> Tuple[Candidate, Offer, Quote, Evidence]:
    """Turn one raw job into (candidate, offer, quote, salary_evidence)."""
    key = entity_key(raw)
    salary = salary_midpoint(raw)
    match = match_ratio(raw, wanted_skills or [])

    candidate = Candidate(
        candidate_id=new_id("jcand"),
        domain="jobs",
        task_id=task_id,
        entity_key=key,
        attributes={
            "title": raw.title,
            "company": raw.company,
            "location": raw.location,
            "job_reference": raw.job_reference,
            "salary_mid": salary,
            "salary_text": raw.salary_text,
            "match_ratio": match,
            "skills": raw.skills,
        },
        source_ids=[raw.marketplace_id],
        is_verified=False,
    )

    offer = Offer(
        offer_id=new_id("joff"),
        candidate_id=candidate.candidate_id,
        marketplace_id=raw.marketplace_id,
        terms={
            "title": raw.title,
            "company": raw.company,
            "location": raw.location,
            "salary_min": raw.salary_min_cny,
            "salary_max": raw.salary_max_cny,
        },
        url=raw.url,
    )

    quote = Quote(
        quote_id=new_id("jquote"),
        offer_id=offer.offer_id,
        price=Money(amount=salary, currency="CNY"),
        method="search",
        confidence=0.85,
        snapshot_reference=raw.job_id,
        source=raw.marketplace_id,
    )

    evidence = Evidence(
        evidence_id=new_id("jevid"),
        field="salary",
        value=salary,
        source=raw.marketplace_id,
        method="job_listing",
        snapshot_reference=raw.job_id,
        confidence=0.85,
    )

    return candidate, offer, quote, evidence
