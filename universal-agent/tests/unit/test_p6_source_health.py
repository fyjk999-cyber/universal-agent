"""P6 — Source Health + Resource Governor。

验收：
1. SourceHealthTracker：记录 latency/success_rate/parser_success/
   price_consistency/last_success/last_failure/consecutive_failure
2. 状态机：连续失败 → HEALTHY→DEGRADED→UNAVAILABLE；恢复 → 回 HEALTHY
3. ResourceGovernor：API/Browser/LLM token/verification budget 配额，超限拒绝
4. 健康状态持久化（SQLite）
"""
from __future__ import annotations

from pathlib import Path

import pytest


def test_source_health_record_and_status(tmp_path: Path) -> None:
    from universal_agent.adapters.health import SourceHealthTracker
    from universal_agent.persistence import Database, SqliteSourceHealthRepository

    db = Database(tmp_path / "ua.db")
    tracker = SourceHealthTracker(SqliteSourceHealthRepository(db))
    tracker.record_success("bing", latency_ms=1200)
    tracker.record_success("bing", latency_ms=800)
    h = tracker.get("bing")
    assert h["status"] == "HEALTHY"
    assert h["success_rate"] == 1.0
    assert h["consecutive_failure"] == 0
    db.close()


def test_consecutive_failures_degrade(tmp_path: Path) -> None:
    from universal_agent.adapters.health import SourceHealthTracker
    from universal_agent.persistence import Database, SqliteSourceHealthRepository

    db = Database(tmp_path / "ua.db")
    tracker = SourceHealthTracker(SqliteSourceHealthRepository(db))
    for _ in range(tracker.degrade_after):
        tracker.record_failure("qunar", error="timeout")
    h = tracker.get("qunar")
    assert h["status"] == "DEGRADED"
    # 更多失败 → UNAVAILABLE
    for _ in range(tracker.degrade_after):
        tracker.record_failure("qunar", error="timeout")
    assert tracker.get("qunar")["status"] == "UNAVAILABLE"
    db.close()


def test_recovery_after_success(tmp_path: Path) -> None:
    from universal_agent.adapters.health import SourceHealthTracker
    from universal_agent.persistence import Database, SqliteSourceHealthRepository

    db = Database(tmp_path / "ua.db")
    tracker = SourceHealthTracker(SqliteSourceHealthRepository(db))
    for _ in range(tracker.degrade_after * 2):
        tracker.record_failure("ctrip", error="x")
    assert tracker.get("ctrip")["status"] == "UNAVAILABLE"
    # 一次成功 → 恢复 DEGRADED → 再成功 → HEALTHY
    tracker.record_success("ctrip", latency_ms=500)
    assert tracker.get("ctrip")["status"] in ("DEGRADED", "HEALTHY")
    db.close()


def test_governor_budget_enforced(tmp_path: Path) -> None:
    from universal_agent.adapters.health import ResourceGovernor

    g = ResourceGovernor(budget={"api_calls": 10, "browser_calls": 3, "llm_tokens": 5000})
    for _ in range(10):
        assert g.consume("api_calls") is True
    # 超限 → 拒绝（fail-closed）
    assert g.consume("api_calls") is False
    assert g.can("browser_calls")
    g.consume("browser_calls")
    g.consume("browser_calls")
    assert g.consume("browser_calls") is True
    assert g.consume("browser_calls") is False


def test_governor_unknown_resource_defaults_deny(tmp_path: Path) -> None:
    from universal_agent.adapters.health import ResourceGovernor

    g = ResourceGovernor(budget={})
    # 未在预算内的资源默认拒绝（不静默放行）
    assert g.consume("unbudgeted") is False


def test_health_persists(tmp_path: Path) -> None:
    from universal_agent.adapters.health import SourceHealthTracker
    from universal_agent.persistence import Database, SqliteSourceHealthRepository

    db = Database(tmp_path / "ua.db")
    repo = SqliteSourceHealthRepository(db)
    SourceHealthTracker(repo).record_success("bing", latency_ms=100)
    # 重启
    h = SourceHealthTracker(repo).get("bing")
    assert h is not None and h["status"] == "HEALTHY"
    db.close()
