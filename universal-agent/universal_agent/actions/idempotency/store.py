"""Idempotency store (§38) — every side-effecting action has an idempotency_key.

防止网络超时→重复下单。同一 (key, action, target) 的重复执行返回首次结果。
Phase 6: JSON 文件持久化（可换 Redis/DB）。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

log = logging.getLogger("ua.actions.idempotency")


class DuplicateRequest(RuntimeError):
    """同一 idempotency_key 已处理过（结果不同）→ 拒绝而非覆盖。"""


class IdempotencyStore:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._file = self.data_dir / "idempotency.json"
        self._records: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if self._file.exists():
            try:
                self._records = json.loads(self._file.read_text("utf-8"))
            except Exception:  # noqa: BLE001
                log.warning("idempotency.json corrupt; starting empty")

    def _save(self) -> None:
        self._file.write_text(json.dumps(self._records, ensure_ascii=False, indent=2),
                              "utf-8")

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        return self._records.get(key)

    def register(self, key: str, *, action: str, target_key: str,
                 result: Dict[str, Any]) -> Dict[str, Any]:
        """Register a completed execution. Duplicate with different result → error."""
        existing = self._records.get(key)
        if existing is not None:
            if existing.get("result") != result:
                raise DuplicateRequest(
                    f"idempotency_key {key} already used with different result")
            return existing
        rec = {"key": key, "action": action, "target_key": target_key,
               "result": result}
        self._records[key] = rec
        self._save()
        return rec

    def exists(self, key: str) -> bool:
        return key in self._records
