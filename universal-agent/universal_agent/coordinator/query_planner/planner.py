"""Query Planner (§24) — answers "what to search?".

Generates concrete flight queries from a TaskSpec search space:
  origin × departure-date × return-date (nights rule).
Pure deterministic expansion; bounded to avoid combinatorial explosion.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import List

from ...core.contracts import TaskSpec


@dataclass(frozen=True)
class FlightQuery:
    origin: str
    destination: str
    depart_date: str  # YYYY-MM-DD
    return_date: str  # YYYY-MM-DD
    nights: int


@dataclass
class QueryPlan:
    task_id: str
    queries: List[FlightQuery] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.queries)


def build_query_plan(task: TaskSpec, max_queries: int = 60) -> QueryPlan:
    space = task.search_space
    origins = space.origin or ["HGH"]
    destinations = space.destination or ["ZQN"]
    nights = space.nights or {"min": 6, "preferred": 7, "max": 8}
    dep = space.departure or {"start": "", "end": ""}

    dep_start = date.fromisoformat(dep.get("start")) if dep.get("start") else date.today()
    dep_end = date.fromisoformat(dep.get("end")) if dep.get("end") else dep_start

    min_n, max_n = int(nights.get("min", 6)), int(nights.get("max", 8))
    preferred = int(nights.get("preferred", 7))

    queries: List[FlightQuery] = []
    for origin in origins:
        for dest in destinations:
            d = dep_start
            while d <= dep_end and len(queries) < max_queries:
                nights_candidates = [preferred, min_n, max_n]  # preferred first
                seen: set[int] = set()
                for n in nights_candidates:
                    if n in seen or not (min_n <= n <= max_n):
                        continue
                    seen.add(n)
                    ret = d + timedelta(days=n)
                    queries.append(FlightQuery(
                        origin=origin, destination=dest,
                        depart_date=d.isoformat(), return_date=ret.isoformat(), nights=n))
                    if len(queries) >= max_queries:
                        break
                d += timedelta(days=1)
    return QueryPlan(task_id=task.id, queries=queries)
