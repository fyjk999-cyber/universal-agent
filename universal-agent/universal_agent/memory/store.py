"""Memory store — Memory belongs to Universal Agent, never to the host (§16).

Phase 1: in-memory + JSON file persistence. All records carry scope/domain/task.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List, Optional

from ..core.contracts import MemoryQuery, MemoryRecord, Scope, new_id, utc_now

log = logging.getLogger("ua.memory")


class MemoryStore:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._file = self.data_dir / "memory.json"
        self._records: List[MemoryRecord] = []
        self._load()

    def _load(self) -> None:
        if self._file.exists():
            try:
                raw = json.loads(self._file.read_text("utf-8"))
                self._records = [MemoryRecord.model_validate(r) for r in raw]
            except Exception:  # noqa: BLE001
                log.warning("memory.json corrupt; starting empty")

    def _save(self) -> None:
        self._file.write_text(
            json.dumps([r.model_dump(mode="json") for r in self._records],
                       ensure_ascii=False, indent=2), "utf-8")

    # ---- CRUD ----
    def put(self, scope: Scope, key: str, value, *, domain: Optional[str] = None,
            task_id: Optional[str] = None, kind: str = "fact",
            source: str = "system", expires_at=None) -> MemoryRecord:
        # upsert by (scope, domain, task_id, key)
        for r in self._records:
            if (r.scope == scope and r.key == key and r.domain == domain
                    and r.task_id == task_id):
                r.value = value
                r.updated_at = utc_now()
                r.version += 1
                r.kind = kind
                r.source = source
                self._save()
                return r
        rec = MemoryRecord(
            record_id=new_id("mem"),
            scope=scope, domain=domain, task_id=task_id,
            key=key, value=value, kind=kind, source=source, expires_at=expires_at,
        )
        self._records.append(rec)
        self._save()
        return rec

    def get(self, scope: Scope, key: str, *, domain: Optional[str] = None,
            task_id: Optional[str] = None) -> Optional[MemoryRecord]:
        for r in self._records:
            if (r.scope == scope and r.key == key and r.domain == domain
                    and r.task_id == task_id):
                return r
        return None

    def query(self, q: MemoryQuery) -> List[MemoryRecord]:
        out = []
        for r in self._records:
            if q.scope is not None and r.scope != q.scope:
                continue
            if q.domain is not None and r.domain != q.domain:
                continue
            if q.task_id is not None and r.task_id != q.task_id:
                continue
            if q.key is not None and r.key != q.key:
                continue
            if q.kind is not None and r.kind != q.kind:
                continue
            out.append(r)
        return out[: q.limit]

    def delete(self, record_id: str) -> bool:
        before = len(self._records)
        self._records = [r for r in self._records if r.record_id != record_id]
        if len(self._records) != before:
            self._save()
            return True
        return False
