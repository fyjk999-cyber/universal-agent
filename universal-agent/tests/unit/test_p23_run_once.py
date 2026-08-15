"""P23 — FR-030 `run_task_once()` 真实执行（RED→GREEN）。

SPAC 要求：`run_task_once()` 不得保留 `not_implemented`；必须真正执行一次扫描
并返回结构化结果。本文件先定义期望行为（RED），实现后转 GREEN。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from universal_agent.coordinator.task_coordinator import (
    TaskCommandError,
    TaskCoordinator,
    sqlite_task_coordinator,
)
from universal_agent.hosts.deepseek_harness import HarnessHostAdapter
from universal_agent.hosts.jarvis import MockJarvisHostAdapter
from universal_agent.persistence import Database, SqliteScanRunRepository
from universal_agent.core.contracts import ScanRunStatus

BASE = Path(__file__).resolve().parent.parent.parent


def _flight_runner(fixtures: Path, sources: list[str], notifier=None):
    """与 apps/scheduler.py 同构的真实 flight runner（replay fixture）。"""
    from universal_agent.adapters.replay import make_fetchers
    from universal_agent.coordinator.scanner import ShadowScanCoordinator
    from universal_agent.events import InProcessEventBus
    from universal_agent.memory import ObservationStore
    from universal_agent.registry import MarketplaceManifest, SkillRegistry

    reg = SkillRegistry()
    for mid in sources:
        reg.register_marketplace(MarketplaceManifest(
            id=mid, domains=["flight"], health="HEALTHY",
            capabilities={"search": True}, trust={"default_score": 0.9}))

    async def runner(task):
        coord = ShadowScanCoordinator(
            bus=InProcessEventBus(), registry=reg,
            observations=ObservationStore(Path("/tmp/ua-p23-obs")),
            fetchers=make_fetchers(fixtures, sources), max_queries=10,
            notifier=notifier)
        return (await coord.scan(task)).summary()

    return runner


FIXTURES = BASE / "tests" / "replay" / "fixtures"


class TestRunTaskOnce:
    def test_run_task_once_executes_real_scan(self, tmp_path: Path, queenstown_watch):
        """有 runner 时：真正执行扫描并返回结构化结果（非 not_implemented）。"""
        from universal_agent.persistence import SqliteTaskRepository
        db = Database(tmp_path / "ua.db")
        coord = TaskCoordinator(SqliteTaskRepository(db))
        scan_runs = SqliteScanRunRepository(db)
        harness = HarnessHostAdapter(
            coordinator=coord, scan_runner=_flight_runner(FIXTURES, ["ctrip", "fliggy"]),
            scan_runs=scan_runs)
        created = harness.create_task(queenstown_watch)

        result = harness.run_task_once(created.id)

        assert result["status"] == "completed", f"unexpected: {result}"
        assert result["task_id"] == created.id
        assert "result" in result
        assert result["result"]["raw_listings"] > 0, "扫描必须真实产出 raw_listings"
        # ScanRun 必须被记录（RULE-003 追踪）
        run = scan_runs.latest_for(created.id)
        assert run is not None and run.status == ScanRunStatus.SUCCESS

    def test_run_task_once_without_runner_raises_explicit(
            self, tmp_path: Path, queenstown_watch):
        """无 runner：显式失败（TaskCommandError），绝不是静默 not_implemented。"""
        coord = sqlite_task_coordinator(tmp_path / "ua.db")
        harness = HarnessHostAdapter(coordinator=coord)
        created = harness.create_task(queenstown_watch)
        with pytest.raises(TaskCommandError):
            harness.run_task_once(created.id)

    def test_run_task_once_unknown_task_raises(self, tmp_path: Path):
        """未知 task：显式失败。"""
        coord = sqlite_task_coordinator(tmp_path / "ua.db")
        harness = HarnessHostAdapter(coordinator=coord, scan_runner=lambda t: None)
        with pytest.raises(TaskCommandError):
            harness.run_task_once("no-such-task")

    def test_run_task_once_jarvis_same_contract(self, tmp_path: Path, queenstown_watch):
        """Jarvis 适配器同一契约（Host Swap 后 run_task_once 仍可用）。"""
        db = Database(tmp_path / "ua.db")
        from universal_agent.persistence import SqliteTaskRepository
        coord = TaskCoordinator(SqliteTaskRepository(db))
        scan_runs = SqliteScanRunRepository(db)
        jarvis = MockJarvisHostAdapter(
            coordinator=coord, scan_runner=_flight_runner(FIXTURES, ["ctrip"]),
            scan_runs=scan_runs)
        created = jarvis.create_task(queenstown_watch)
        result = jarvis.run_task_once(created.id)
        assert result["status"] == "completed"
        assert result["result"]["raw_listings"] > 0
        assert jarvis.get_host_user_context()["host"] == "jarvis"


class TestNotificationDelivery:
    """FR-031：机会通知真实送达（持久化 + sink），不是只写日志。"""

    def test_scan_notification_reaches_host_sink_and_sqlite(
            self, tmp_path: Path, queenstown_watch):
        from universal_agent.persistence import SqliteNotificationRepository
        from universal_agent.persistence import SqliteTaskRepository

        db = Database(tmp_path / "ua.db")
        coord = TaskCoordinator(SqliteTaskRepository(db))
        notifications = SqliteNotificationRepository(db)
        delivered: list = []
        harness = HarnessHostAdapter(
            coordinator=coord,
            scan_runner=_flight_runner(
                FIXTURES, ["ctrip", "fliggy"],
                notifier=lambda n: harness.send_notification(n)),
            scan_runs=SqliteScanRunRepository(db),
            notifications=notifications,
            notification_sink=delivered.append)
        created = harness.create_task(queenstown_watch)

        result = harness.run_task_once(created.id)

        assert result["status"] == "completed"
        # 机会通知必须真实到达投递通道（sink）
        assert len(delivered) >= 1, "机会通知必须送达 sink"
        assert delivered[0]["event_type"] == "OPPORTUNITY_DETECTED"
        # 且持久化到 SQLite（跨重启可查，FR-160）
        assert notifications.get(_fp(delivered[0])) is not None

    def test_send_notification_persists_without_sink(
            self, tmp_path: Path, queenstown_watch):
        """无 sink 时也持久化（仅日志降级，不静默丢失）。"""
        from universal_agent.persistence import SqliteNotificationRepository
        db = Database(tmp_path / "ua.db")
        notifications = SqliteNotificationRepository(db)
        harness = HarnessHostAdapter(coordinator=None, notifications=notifications)
        harness.send_notification({"task_id": "t1", "title": "x"})
        row = notifications.get(_fp({"task_id": "t1", "title": "x"}))
        assert row is not None and row["title"] == "x"

    def test_fr164_event_types_declared(self):
        """FR-164：通知事件分类必须存在。"""
        from universal_agent.events import EventType
        for name in ("PRICE_DROP", "RARE_OPPORTUNITY", "AVAILABILITY_CHANGE",
                     "WATCH_FAILED", "APPROVAL_REQUIRED", "ACTION_RESULT"):
            assert hasattr(EventType, name), f"missing EventType.{name}"


def _fp(notification: dict) -> str:
    from universal_agent.hosts.deepseek_harness.adapter import _notification_fingerprint
    return _notification_fingerprint(notification)


class TestApprovalFlow:
    """FR-032：审批真实流转（请求持久化 → 用户决策 APPROVED/DENIED）。"""

    @pytest.fixture
    def inbox_svc(self, tmp_path: Path):
        from universal_agent.actions.approval import ApprovalInbox
        from universal_agent.persistence import (
            Database, SqliteApprovalRepository, SqliteTaskRepository)
        from universal_agent.coordinator.task_coordinator import TaskCoordinator
        db = Database(tmp_path / "ua.db")
        coord = TaskCoordinator(SqliteTaskRepository(db))
        inbox = ApprovalInbox(repo=SqliteApprovalRepository(db))
        harness = HarnessHostAdapter(coordinator=coord, approval_inbox=inbox)
        return harness, inbox, db

    def test_request_creates_real_persisted_approval(self, inbox_svc):
        harness, inbox, db = inbox_svc
        resp = harness.request_approval(
            {"type": "purchase", "title": "买机票 ¥3980", "task_id": "t1"})
        assert resp["status"] == "PENDING"
        assert resp["approval_id"].startswith("ap_")
        # 持久化到 SQLite（RULE-003）
        item = inbox.get(resp["approval_id"])
        assert item is not None and item["title"] == "买机票 ¥3980"
        assert inbox.pending()

    def test_decide_approves_and_persists(self, inbox_svc):
        harness, inbox, db = inbox_svc
        req = harness.request_approval({"title": "approve me"})
        out = harness.decide_approval(req["approval_id"], approved=True)
        assert out["status"] == "APPROVED" and out["approved"] is True
        assert inbox.get(req["approval_id"])["status"] == "APPROVED"

    def test_decide_rejects(self, inbox_svc):
        harness, inbox, db = inbox_svc
        req = harness.request_approval({"title": "reject me"})
        out = harness.decide_approval(req["approval_id"], approved=False)
        assert out["status"] == "REJECTED" and out["approved"] is False

    def test_decide_twice_rejected(self, inbox_svc):
        harness, inbox, db = inbox_svc
        req = harness.request_approval({"title": "twice"})
        harness.decide_approval(req["approval_id"], approved=True)
        with pytest.raises(ValueError):
            harness.decide_approval(req["approval_id"], approved=True)

    def test_decide_unknown_raises(self, inbox_svc):
        harness, inbox, db = inbox_svc
        with pytest.raises(KeyError):
            harness.decide_approval("ap_nope", approved=True)

    def test_request_without_inbox_raises_explicit(self, tmp_path, queenstown_watch):
        """未装配审批箱：显式失败（不静默返回固定 pending）。"""
        coord = sqlite_task_coordinator(tmp_path / "ua.db")
        harness = HarnessHostAdapter(coordinator=coord)
        with pytest.raises(TaskCommandError):
            harness.request_approval({"title": "x"})

    def test_jarvis_approval_same_contract(self, tmp_path):
        from universal_agent.actions.approval import ApprovalInbox
        from universal_agent.persistence import (
            Database, SqliteApprovalRepository, SqliteTaskRepository)
        from universal_agent.coordinator.task_coordinator import TaskCoordinator
        db = Database(tmp_path / "ua.db")
        coord = TaskCoordinator(SqliteTaskRepository(db))
        jarvis = MockJarvisHostAdapter(
            coordinator=coord, approval_inbox=ApprovalInbox(repo=SqliteApprovalRepository(db)))
        req = jarvis.request_approval({"title": "jarvis approve"})
        out = jarvis.decide_approval(req["approval_id"], approved=True)
        assert out["status"] == "APPROVED"


class TestRule003SqliteBackends:
    """RULE-003：approvals/idempotency/dedup/killswitch 状态 SQLite 化，跨重启保持。"""

    def test_idempotency_sqlite_survives_restart(self, tmp_path: Path):
        from universal_agent.actions.idempotency import IdempotencyStatus, IdempotencyStore
        from universal_agent.persistence import Database, SqliteKvRepository
        db = Database(tmp_path / "ua.db")
        s1 = IdempotencyStore(repo=SqliteKvRepository(db, "idempotency"))
        s1.reserve("k1", action="buy", target_key="offer1")
        s1.mark_committed("k1")
        s1.finalize("k1", {"status": "EXECUTED"})
        s2 = IdempotencyStore(repo=SqliteKvRepository(db, "idempotency"))
        assert s2.status("k1") == IdempotencyStatus.FINALIZED
        assert s2.get("k1")["result"]["status"] == "EXECUTED"

    def test_dedup_sqlite_survives_restart(self, tmp_path: Path):
        from universal_agent.notifications import NotificationDedup
        from universal_agent.persistence import Database, SqliteKvRepository
        db = Database(tmp_path / "ua.db")
        d1 = NotificationDedup(repo=SqliteKvRepository(db, "notification_dedup"))
        d1.record("t1", "offer1", {"price": 100})
        d2 = NotificationDedup(repo=SqliteKvRepository(db, "notification_dedup"))
        assert not d2.should_notify("t1", "offer1", {"price": 100}), "重启后 cooldown 必须生效"

    def test_killswitch_sqlite_survives_restart(self, tmp_path: Path):
        from universal_agent.actions.policy import KillSwitch, KillSwitchTripped
        from universal_agent.persistence import Database, SqliteKvRepository
        db = Database(tmp_path / "ua.db")
        k1 = KillSwitch(repo=SqliteKvRepository(db, "killswitch"))
        k1.kill("emergency")
        k2 = KillSwitch(repo=SqliteKvRepository(db, "killswitch"))
        assert k2.is_killed(), "重启后 KillSwitch 必须保持 killed"
        with pytest.raises(KillSwitchTripped):
            k2.assert_alive()

    def test_service_wires_all_repos_sqlite(self, tmp_path: Path):
        from universal_agent.service import UniversalAgentService
        svc = UniversalAgentService(tmp_path / "data")
        try:
            for attr in ("tasks", "scan_runs", "memory", "events", "outbox",
                         "observations", "notifications", "approvals", "actions",
                         "audit", "source_health",
                         "idempotency_kv", "dedup_kv", "killswitch_kv"):
                assert getattr(svc.repos, attr) is not None, f"repo {attr} 未装配"
            assert svc.idempotency is not None
            assert svc.notification_dedup is not None
            assert svc.killswitch is not None
        finally:
            svc.close()
