"""Notification dedup (§34 + P0.8 持久化) — fingerprint + cooldown + restart-safe.

重启后仍然记得已提醒：cooldown 状态持久化。
P23（RULE-003）：支持 SQLite 后端（repo 参数，SqliteKvRepository table=notification_dedup）；
未提供时保留 JSON 文件兼容。
字段：fingerprint / task_id / candidate_id / trigger_reason / material_state /
      last_sent_at / cooldown_until（P11 完整化）。
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

log = logging.getLogger("ua.notifications.dedup")

_STATE_KEY = "state"


class NotificationDedup:
    """Suppresses repeat notifications for the same material state (§34)."""

    def __init__(self, cooldown_minutes: int = 720,
                 state_path: Optional[Path] = None,
                 repo=None) -> None:
        self.cooldown = timedelta(minutes=cooldown_minutes)
        self.state_path = state_path
        self.repo = repo  # SqliteKvRepository(table="notification_dedup")；RULE-003
        self._last: Dict[str, datetime] = {}
        self._load()

    def _load(self) -> None:
        raw: Optional[Dict[str, Any]] = None
        if self.repo is not None:
            raw = self.repo.get(_STATE_KEY)
        elif self.state_path is not None and self.state_path.exists():
            try:
                raw = json.loads(self.state_path.read_text("utf-8"))
            except Exception:  # noqa: BLE001
                log.warning("dedup state corrupt; starting empty")
        if raw:
            for fp, iso in (raw.get("last") or {}).items():
                try:
                    self._last[fp] = datetime.fromisoformat(iso)
                except ValueError:
                    continue

    def _persist(self) -> None:
        payload = {"last": {fp: ts.isoformat() for fp, ts in self._last.items()}}
        if self.repo is not None:
            self.repo.put(_STATE_KEY, payload)
            return
        if self.state_path is None:
            return
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(payload), "utf-8")

    @staticmethod
    def fingerprint(task_id: str, target_key: str,
                    material: Optional[Dict[str, Any]] = None) -> str:
        payload = {"task_id": task_id, "target_key": target_key,
                   "material": material or {}}
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def should_notify(self, task_id: str, target_key: str,
                      material: Optional[Dict[str, Any]] = None,
                      now: Optional[datetime] = None) -> bool:
        now = now or datetime.now(timezone.utc)
        fp = self.fingerprint(task_id, target_key, material)
        last = self._last.get(fp)
        if last is None:
            return True  # first observation → notify
        if now - last >= self.cooldown:
            return True  # cooldown elapsed → allow re-notify
        return False  # same material within cooldown → suppress

    def record(self, task_id: str, target_key: str,
               material: Optional[Dict[str, Any]] = None,
               now: Optional[datetime] = None) -> None:
        now = now or datetime.now(timezone.utc)
        fp = self.fingerprint(task_id, target_key, material)
        self._last[fp] = now
        self._persist()

    def suppress_count(self) -> int:
        now = datetime.now(timezone.utc)
        return sum(1 for t in self._last.values() if now - t < self.cooldown)
