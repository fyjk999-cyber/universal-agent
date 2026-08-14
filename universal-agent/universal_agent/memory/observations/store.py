"""Observation Store (§29) — facts only, immutable, JSON-persisted.

Observations are never directly modified by LLM; they back
historical-low / price-trend / platform-truth analysis.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List, Optional

from ...core.contracts import Money, Observation, Quote, new_id

log = logging.getLogger("ua.observations")


class ObservationStore:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._file = self.data_dir / "observations.json"
        self._observations: List[Observation] = []
        self._load()

    def _load(self) -> None:
        if self._file.exists():
            try:
                raw = json.loads(self._file.read_text("utf-8"))
                self._observations = [Observation.model_validate(r) for r in raw]
            except Exception:  # noqa: BLE001
                log.warning("observations.json corrupt; starting empty")

    def _save(self) -> None:
        self._file.write_text(
            json.dumps([o.model_dump(mode="json") for o in self._observations],
                       ensure_ascii=False, indent=2), "utf-8")

    def record_price(self, quote: Quote, task_id: str, domain: str = "flight",
                     entity_key: Optional[str] = None) -> Observation:
        """Record a price fact. target_key defaults to offer_id; pass
        entity_key to accumulate history across scans of the same real
        itinerary (§21, §32 historical stats)."""
        obs = Observation(
            observation_id=new_id("obs"),
            task_id=task_id,
            domain=domain,
            kind="price",
            target_key=entity_key or quote.offer_id,
            value=quote.price.amount,
            unit=quote.price.currency,
            evidence_refs=[quote.snapshot_reference] if quote.snapshot_reference else [],
        )
        self._observations.append(obs)
        self._save()
        return obs

    def price_history(self, target_key: str) -> List[float]:
        return [float(o.value) for o in self._observations
                if o.kind == "price" and o.target_key == target_key]

    def latest_quote_for(self, offer_id: str) -> Optional[float]:
        values = self.price_history(offer_id)
        return values[-1] if values else None

    def quotes_history(self, entity_key: str) -> List[Quote]:
        """Reconstruct Quote-like history for one entity across scans (§32)."""
        out = []
        for o in self._observations:
            if o.kind == "price" and o.target_key == entity_key:
                out.append(Quote(
                    quote_id=new_id("qh"),
                    offer_id=o.target_key,
                    price=Money(amount=float(o.value), currency=o.unit or "CNY"),
                    observed_at=o.observed_at,
                    source="observation_history",
                ))
        return out

    def list_all(self) -> List[Observation]:
        return list(self._observations)
