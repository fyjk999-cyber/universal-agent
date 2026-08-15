"""CH2-2.6 — Harness 重启恢复 Acceptance Flow（SPAC §36）。

Acceptance Flow:
  Harness → Create Watch → Persist → Scan → Opportunity → Notification
  → Pause → Resume → 【Restart Harness（同 data_dir 新服务实例）】
  → Watch Restored → Scan Continues

模拟"Harness 重启"：关闭服务实例（释放 SQLite）→ 用同一 data_dir 新建实例
（等价于 DSH 重启后重新装配）→ 验证 Watch/ScanRun/通知/审批全部从 SQLite 恢复。
"""
from __future__ import annotations

from pathlib import Path

from universal_agent.core.contracts import TriggerRule, WatchState
from universal_agent.service import UniversalAgentService

BASE = Path(__file__).resolve().parent.parent.parent


def _flight_runner(fixtures: Path, sources: list[str], notifier=None):
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
            observations=ObservationStore(Path("/tmp/ua-ch2-obs")),
            fetchers=make_fetchers(fixtures, sources), max_queries=10,
            notifier=notifier)
        return (await coord.scan(task)).summary()

    return runner


class TestChapter2AcceptanceFlow:
    """SPAC §36 完整 Acceptance Flow（含 Harness 重启恢复）。"""

    def test_full_flow_with_restart_recovery(self, tmp_path: Path, queenstown_watch):
        data_dir = tmp_path / "data"
        fixtures = BASE / "tests" / "replay" / "fixtures"

        # ---- 阶段 1：Harness 会话（Create → Persist → Scan → Notify）----
        svc1 = UniversalAgentService(data_dir)
        try:
            # 装配真实投递（sink 记录 + SQLite 持久化）
            delivered: list = []
            svc1.adapter.notification_sink = delivered.append
            svc1.adapter.scan_runner = _flight_runner(
                fixtures, ["ctrip", "fliggy"], notifier=svc1.adapter.send_notification)

            # 1) CREATE WATCH（带触发规则，确保机会通知真实触发）
            watch = queenstown_watch.model_copy(update={
                "notify_if": TriggerRule(opportunity_score_gte=50)})
            created = svc1.adapter.create_task(watch)
            assert created.state == WatchState.DRAFT

            # 2) 激活 → SCAN（run_task_once，P23）
            activated = created.model_copy(update={"state": WatchState.ACTIVE})
            svc1.adapter.update_task(activated)
            result = svc1.adapter.run_task_once(created.id)
            assert result["status"] == "completed"
            assert result["result"]["raw_listings"] > 0

            # 3) OPPORTUNITY → NOTIFICATION（真实送达 + 持久化）
            assert len(delivered) >= 1, "机会通知必须送达"
            assert delivered[0]["event_type"] == "OPPORTUNITY_DETECTED"
            assert svc1.health()["healthy"] is True, "healthcheck 必须通过"

            # 4) PAUSE（ACTIVE→PAUSED）
            paused = svc1.adapter.pause_task(created.id)
            assert paused.state == WatchState.PAUSED
        finally:
            svc1.close()  # ← 模拟 Harness 重启（释放 SQLite）

        # ---- 阶段 2：Harness 重启（同 data_dir 新实例）----
        svc2 = UniversalAgentService(data_dir)
        try:
            # 5) WATCH RESTORED（SQLite 恢复）
            restored = svc2.adapter.get_task(created.id)
            assert restored is not None, "重启后 Watch 必须恢复"
            assert restored.state == WatchState.PAUSED
            assert restored.scan_count >= 1, "scan_count 必须持久化"

            # 6) RESUME（PAUSED→WATCHING）
            resumed = svc2.adapter.resume_task(created.id)
            assert resumed.state == WatchState.WATCHING

            # 7) SCAN CONTINUES（重启后再次扫描）
            delivered2: list = []
            svc2.adapter.notification_sink = delivered2.append
            svc2.adapter.scan_runner = _flight_runner(
                fixtures, ["ctrip", "fliggy"], notifier=svc2.adapter.send_notification)
            result2 = svc2.adapter.run_task_once(created.id)
            assert result2["status"] == "completed"
            assert result2["result"]["raw_listings"] > 0

            # 8) 持久化真相跨重启（RULE-003）
            runs = [r for r in svc2.repos.scan_runs.list_all()
                    if r.task_id == created.id]
            assert len(runs) >= 2, "两次扫描的 ScanRun 必须都在 SQLite"
            assert all(r.status.value == "SUCCESS" for r in runs)
            # 通知记录持久化
            assert svc2.repos.notifications.get(
                _fp(delivered[0])) is not None

            # 9) healthcheck（CH2-2.5）
            h = svc2.health()
            assert h["healthy"] is True, h
        finally:
            svc2.close()


def _fp(notification: dict) -> str:
    from universal_agent.hosts.deepseek_harness.adapter import _notification_fingerprint
    return _notification_fingerprint(notification)
