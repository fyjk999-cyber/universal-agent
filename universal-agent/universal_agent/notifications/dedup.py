"""Notification dedup (§34) — fingerprint + material change + cooldown."""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

log = logging.getLogger("ua.notifications.dedup")


class NotificationDedup:
    """Suppresses repeat notifications for the same material state.

    Rules (§34):
      - fingerprint = hash(candidate_key + material fields)
      - identical fingerprint within cooldown → suppress
      - a *material change* (fingerprint differs) resets cooldown and notifies
    """

    def __init__(self, cooldown_minutes: int = 720) -> None:
        self.cooldown = timedelta(minutes=cooldown_minutes)
        self._last: Dict[str, datetime] = {}

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

    def suppress_count(self) -> int:
        """Number of currently-cooldown fingerprints (for metrics §52)."""
        now = datetime.now(timezone.utc)
        return sum(1 for t in self._last.values() if now - t < self.cooldown)
