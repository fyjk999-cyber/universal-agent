"""Idempotency Store（§38 + P0.5 升级）— reserve/finalize/reconcile。

状态机：RESERVED → COMMITTED → FINALIZED | FAILED | UNKNOWN
- reserve: 执行前登记（防重复）
- finalize: 完成后定稿
- 若 commit 后崩溃但 finalize 前崩溃 → 状态 UNKNOWN/RESERVED
  → reconcile() 查询平台真实状态再决定（防双订单）

P23（RULE-003）：支持 SQLite 后端（repo 参数，SqliteKvRepository table=idempotency）；
未提供时保留 JSON 文件兼容。
"""
from __future__ import annotations

import json
import logging
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional

log = logging.getLogger("ua.actions.idempotency")


class IdempotencyStatus(str, Enum):
    RESERVED = "RESERVED"
    COMMITTED = "COMMITTED"
    FINALIZED = "FINALIZED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


class DuplicateRequest(RuntimeError):
    """同一 idempotency_key 已 FINALIZED（结果不同）→ 拒绝。"""


class IdempotencyStore:
    def __init__(self, data_dir: Optional[Path] = None, repo=None) -> None:
        self.repo = repo  # SqliteKvRepository(table="idempotency")；RULE-003
        self.data_dir = Path(data_dir) if data_dir is not None else None
        if self.data_dir is not None:
            self.data_dir.mkdir(parents=True, exist_ok=True)
        self._file = (self.data_dir / "idempotency.json") if self.data_dir is not None else None
        self._records: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if self.repo is not None:
            for rec in self.repo.list_all():
                self._records[rec["key"]] = rec
            return
        if self._file is not None and self._file.exists():
            try:
                self._records = json.loads(self._file.read_text("utf-8"))
            except Exception:  # noqa: BLE001
                log.warning("idempotency.json corrupt; starting empty")

    def _save(self) -> None:
        if self.repo is not None:
            for rec in self._records.values():
                self.repo.put(rec["key"], rec)
            return
        if self._file is not None:
            self._file.write_text(json.dumps(self._records, ensure_ascii=False, indent=2),
                                  "utf-8")

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        return self._records.get(key)

    def status(self, key: str) -> Optional[IdempotencyStatus]:
        rec = self._records.get(key)
        if rec is None:
            return None
        return IdempotencyStatus(rec.get("status", IdempotencyStatus.RESERVED.value))

    def reserve(self, key: str, *, action: str, target_key: str) -> Dict[str, Any]:
        """执行前登记。若已 FINALIZED 同 key → DuplicateRequest。"""
        existing = self._records.get(key)
        if existing is not None:
            if existing.get("status") == IdempotencyStatus.FINALIZED.value:
                raise DuplicateRequest(
                    f"idempotency_key {key} already finalized")
            if existing.get("status") in (
                    IdempotencyStatus.RESERVED.value,
                    IdempotencyStatus.COMMITTED.value,
                    IdempotencyStatus.UNKNOWN.value):
                # 进行中 → 可能是崩溃残留，返回现有（调用方应 reconcile）
                return existing
        rec = {"key": key, "action": action, "target_key": target_key,
               "status": IdempotencyStatus.RESERVED.value,
               "result": None}
        self._records[key] = rec
        self._save()
        return rec

    def mark_committed(self, key: str) -> None:
        if key in self._records:
            self._records[key]["status"] = IdempotencyStatus.COMMITTED.value
            self._save()

    def finalize(self, key: str, result: Dict[str, Any],
                 status: IdempotencyStatus = IdempotencyStatus.FINALIZED) -> Dict[str, Any]:
        """定稿（成功或失败终态）。"""
        rec = self._records.get(key)
        if rec is None:
            rec = {"key": key, "action": "unknown", "target_key": "",
                   "status": status.value, "result": result}
            self._records[key] = rec
        else:
            rec["status"] = status.value
            rec["result"] = result
        self._save()
        return rec

    def mark_unknown(self, key: str) -> None:
        """commit 后崩溃场景：执行状态未知，待 reconcile。"""
        if key in self._records:
            self._records[key]["status"] = IdempotencyStatus.UNKNOWN.value
            self._save()

    def reconcile(self, key: str, reconcile_fn) -> Optional[Dict[str, Any]]:
        """查询平台真实状态；据实定稿（防双订单）。"""
        rec = self._records.get(key)
        if rec is None or rec.get("status") != IdempotencyStatus.UNKNOWN.value:
            return rec
        platform_state = reconcile_fn(key)
        if platform_state.get("confirmed"):
            return self.finalize(key, {"status": "EXECUTED", **platform_state})
        # 平台未确认 → 视为未执行，可安全重试
        return self.finalize(key, {"status": "NOT_CONFIRMED"},
                             status=IdempotencyStatus.FAILED)

    def unresolved(self) -> list[str]:
        """UNKNOWN/RESERVED/COMMITTED 残留（重启后需 reconcile）。"""
        return [k for k, v in self._records.items()
                if v.get("status") in (IdempotencyStatus.UNKNOWN.value,
                                       IdempotencyStatus.RESERVED.value,
                                       IdempotencyStatus.COMMITTED.value)]

    def exists(self, key: str) -> bool:
        return key in self._records
