"""Replay source adapter (§47) — loads RawListing fixtures from disk.

Allows deterministic replay of scans (Normalize/Dedup/Score/Verify/Decide)
without touching real platforms. Fixtures are saved RawListing JSON arrays,
one file per source.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Callable, Dict, List

from universal_agent.coordinator.query_planner import FlightQuery
from universal_agent.core.contracts import RawHotel, RawJob, RawListing

log = logging.getLogger("ua.adapters.replay")


def load_fixtures(fixtures_dir: Path, source_id: str):
    """Load a fixture file. Detects type by content:
    RawListing (flight) / RawHotel / RawJob. Returns parsed objects."""
    path = Path(fixtures_dir) / f"{source_id}.json"
    if not path.exists():
        return []
    raw = json.loads(path.read_text("utf-8"))
    if not raw:
        return []
    first = raw[0]
    if "origin_airport" in first or "outbound" in first:
        return [RawListing.model_validate(r) for r in raw]
    if "hotel_id" in first or "room_name" in first:
        return [RawHotel.model_validate(r) for r in raw]
    if "job_id" in first or "company" in first and "title" in first:
        return [RawJob.model_validate(r) for r in raw]
    return raw


def make_fetcher(fixtures_dir: Path, source_id: str,
                 date_filter: bool = True) -> Callable[[FlightQuery], List[RawListing]]:
    """Return a fetch function: query → matching raw listings for that source.

    A real source returns listings only for the queried origin + date, so the
    replay adapter matches on BOTH (origin_airport, depart_date) to avoid
    cross-query duplication. `date_filter=False` returns everything (used by
    tests to inspect fixture shape only).
    """
    fixtures = load_fixtures(fixtures_dir, source_id)

    def fetch(query: FlightQuery) -> List[RawListing]:
        if not date_filter:
            return fixtures
        return [f for f in fixtures
                if f.origin_airport == query.origin
                and f.depart_date == query.depart_date
                and f.return_date == query.return_date]

    return fetch


def make_fetchers(fixtures_dir: Path,
                  sources: List[str]) -> Dict[str, Callable[[FlightQuery], List[RawListing]]]:
    return {sid: make_fetcher(fixtures_dir, sid) for sid in sources}
