"""SqliteMemoryStore（P1.5 + P3）— Memory 迁移到 DB。

支持 GLOBAL/DOMAIN/TASK/SESSION；自动过滤 expired。
P3：user_id/profile_id/confidence；kind 过滤（8 子域检索）。
"""
from __future__ import annotations

from typing import List, Optional

from ..core.contracts import MemoryQuery, MemoryRecord, Scope, new_id, utc_now
from ..persistence import Database


class SqliteMemoryStore:
    def __init__(self, db: Database) -> None:
        self.db = db

    def put(self, scope: Scope, key: str, value, *, domain: Optional[str] = None,
            task_id: Optional[str] = None, kind: str = "fact",
            source: str = "system", expires_at=None,
            user_id: Optional[str] = None,
            profile_id: Optional[str] = None,
            confidence: Optional[float] = None) -> MemoryRecord:
        # upsert 语义：先查同 (scope,key,domain,task_id,user_id)
        existing = self._find(scope, key, domain, task_id, user_id)
        if existing is not None:
            existing.value = value
            existing.updated_at = utc_now()
            existing.version += 1
            existing.kind = kind
            if expires_at is not None:
                existing.expires_at = expires_at
            existing.source = source
            if confidence is not None:
                existing.confidence = confidence
            self._save(existing)
            return existing
        rec = MemoryRecord(
            record_id=new_id("mem"), scope=scope, domain=domain, task_id=task_id,
            key=key, value=value, kind=kind, source=source, expires_at=expires_at,
            user_id=user_id, profile_id=profile_id, confidence=confidence)
        self._save(rec)
        return rec

    def get(self, scope: Scope, key: str, *, domain: Optional[str] = None,
            task_id: Optional[str] = None,
            user_id: Optional[str] = None) -> Optional[MemoryRecord]:
        rec = self._find(scope, key, domain, task_id, user_id)
        if rec is None:
            return None
        if self._expired(rec):
            return None  # expired 自动过滤（P1.5）
        return rec

    def query(self, q: MemoryQuery) -> List[MemoryRecord]:
        return SqliteMemoryRepository(self.db).query(q)

    def _find(self, scope: Scope, key: str, domain, task_id,
              user_id=None) -> Optional[MemoryRecord]:
        import json
        rows = self.db.query_all(
            "SELECT data FROM memories WHERE scope=? AND key=? "
            "AND (task_id IS ? OR task_id=? OR ? IS NULL)",
            (scope.value, key, task_id, task_id, task_id))
        for r in rows:
            rec = MemoryRecord.model_validate(json.loads(r["data"]))
            if domain is not None and rec.domain != domain:
                continue
            if user_id is not None and rec.user_id != user_id:
                continue
            return rec
        return None

    def _save(self, rec: MemoryRecord) -> None:
        import json
        self.db.execute(
            "INSERT OR REPLACE INTO memories (record_id, scope, key, task_id, data) "
            "VALUES (?,?,?,?,?)",
            (rec.record_id, rec.scope.value, rec.key, rec.task_id,
             json.dumps(rec.model_dump(mode="json"), ensure_ascii=False)))

    @staticmethod
    def _expired(rec: MemoryRecord) -> bool:
        if rec.expires_at is None:
            return False
        return rec.expires_at <= utc_now()


from ..persistence.repos import SqliteMemoryRepository  # noqa: E402
