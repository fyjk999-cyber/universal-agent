"""Notification dedup tests (§34)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from universal_agent.notifications import NotificationDedup

NOW = datetime(2026, 8, 14, 9, 0, tzinfo=timezone.utc)


class TestNotificationDedup:
    def test_first_observation_notifies(self):
        d = NotificationDedup()
        assert d.should_notify("t1", "c1", {"price": 4380}, now=NOW) is True

    def test_same_material_within_cooldown_suppressed(self):
        d = NotificationDedup(cooldown_minutes=720)
        assert d.should_notify("t1", "c1", {"price": 4380}, now=NOW) is True
        d.record("t1", "c1", {"price": 4380}, now=NOW)
        assert d.should_notify("t1", "c1", {"price": 4380}, now=NOW + timedelta(hours=2)) is False

    def test_material_change_notifies(self):
        d = NotificationDedup()
        d.record("t1", "c1", {"price": 4380}, now=NOW)
        assert d.should_notify("t1", "c1", {"price": 3980}, now=NOW + timedelta(hours=1)) is True

    def test_cooldown_elapsed_reallows(self):
        d = NotificationDedup(cooldown_minutes=60)
        d.record("t1", "c1", {"price": 4380}, now=NOW)
        assert d.should_notify("t1", "c1", {"price": 4380}, now=NOW + timedelta(hours=2)) is True

    def test_fingerprint_stable(self):
        fp1 = NotificationDedup.fingerprint("t1", "c1", {"price": 4380})
        fp2 = NotificationDedup.fingerprint("t1", "c1", {"price": 4380})
        assert fp1 == fp2
        assert len(fp1) == 16
