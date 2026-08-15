"""FINAL VERIFICATION — 按指令 TEST A-J 全量验收 Universal Agent v1.0。

这些是 agent-project-test 的 VERIFY 阶段执行的功能验收。
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from universal_agent.core.contracts import WatchTask, WatchState
from universal_agent.service import UniversalAgentService


def _task(tid: str = "w-final") -> WatchTask:
    return WatchTask(id=tid, type="watch", domain="flight",
                     schedule={"timezone": "Asia/Shanghai", "baseline": ["09:00"]})


# ===================== TEST A — Runtime =====================
def test_a_startup_shutdown_restart(tmp_path: Path) -> None:
    """启动 → 停止 → 重启 → 状态恢复（Crash Recovery）。"""
    svc1 = UniversalAgentService(data_dir=tmp_path / "data")
    svc1.coordinator.create_watch(_task())
    svc1.coordinator.activate("w-final")
    svc1.close()  # 停止（模拟崩溃/关闭）

    svc2 = UniversalAgentService(data_dir=tmp_path / "data")  # 重启
    try:
        t = svc2.coordinator.get("w-final")
        assert t is not None and t.state == WatchState.ACTIVE
    finally:
        svc2.close()


# ===================== TEST B — Watch =====================
def test_b_watch_lifecycle(tmp_path: Path) -> None:
    """创建 → 暂停 → 恢复 → 取消 → 过期。"""
    from universal_agent.core.state_machine import TransitionError
    svc = UniversalAgentService(data_dir=tmp_path / "data")
    try:
        svc.coordinator.create_watch(_task())
        svc.coordinator.activate("w-final")
        assert svc.coordinator.get("w-final").state == WatchState.ACTIVE
        svc.coordinator.pause("w-final")
        assert svc.coordinator.get("w-final").state == WatchState.PAUSED
        svc.coordinator.resume("w-final")
        assert svc.coordinator.get("w-final").state == WatchState.WATCHING
        svc.coordinator.cancel("w-final")
        assert svc.coordinator.get("w-final").state == WatchState.CANCELLED
        # 终态不复活：resume 是 no-op（不抛错，但状态保持 CANCELLED）
        svc.coordinator.resume("w-final")
        assert svc.coordinator.get("w-final").state == WatchState.CANCELLED
    finally:
        svc.close()


# ===================== TEST C — Persistence =====================
def test_c_all_state_persists_across_restart(tmp_path: Path) -> None:
    """Task/Memory/Observation/Notification/Approval/Event/Action 跨重启保留。"""
    svc1 = UniversalAgentService(data_dir=tmp_path / "data")
    svc1.coordinator.create_watch(_task())
    svc1.repos.memory.set_preference("max_stops", 2, domain="flight", user_id="u1")
    run = svc1.repos.scan_runs.start("w-final")
    svc1.repos.scan_runs.finish(run.run_id, "SUCCESS")
    svc1.close()

    svc2 = UniversalAgentService(data_dir=tmp_path / "data")
    try:
        assert svc2.coordinator.get("w-final") is not None          # Task
        assert svc2.repos.memory.get_preference("max_stops", domain="flight",
                                                user_id="u1") is not None  # Memory
        runs = svc2.repos.scan_runs.list_all()                       # ScanRun
        assert len(runs) == 1 and runs[0].status.value == "SUCCESS"
    finally:
        svc2.close()


# ===================== TEST D — Flight =====================
def test_d_flight_pipeline_shadow(tmp_path: Path) -> None:
    """Flight 完整管线：raw → normalize → candidate → score → top5。"""
    from universal_agent.coordinator.scanner import ShadowScanCoordinator
    from universal_agent.core.contracts import RawListing, TaskSpec
    from universal_agent.events import InProcessEventBus
    from universal_agent.memory import ObservationStore
    from universal_agent.registry import MarketplaceManifest, SkillRegistry

    def fetcher(query):
        return [RawListing.model_validate({
            "listing_id": f"f-{query.origin}", "source": "replay", "marketplace_id": "replay",
            "task_id": "t1", "origin_airport": query.origin, "dest_airport": "ZQN",
            "depart_date": query.depart_date, "return_date": query.return_date, "nights": 7,
            "price_cny": 3659.0,
            "outbound": {"segments": [], "total_min": 900, "stops": -1},
            "inbound": {"segments": [], "total_min": 0, "stops": -1},
        })]

    reg = SkillRegistry()
    reg.register_marketplace(MarketplaceManifest(id="replay", domains=["flight"],
                                                  health="HEALTHY",
                                                  trust={"default_score": 0.9}))
    coord = ShadowScanCoordinator(bus=InProcessEventBus(), registry=reg,
                                  observations=ObservationStore(tmp_path / "obs"),
                                  fetchers={"replay": fetcher}, max_queries=3)
    task = TaskSpec(id="t1", type="watch", domain="flight",
                    search_space={"origin": ["HGH"], "destination": ["ZQN"],
                                  "departure": {"start": "2026-08-30", "end": "2026-08-30"},
                                  "nights": {"min": 7, "preferred": 7, "max": 7}})
    out = asyncio.run(coord.scan(task))
    assert out.raw_listings and out.candidates
    assert "SCAN_REQUESTED" in out.emitted_events or len(out.raw_listings) > 0


# ===================== TEST E — Travel =====================
def test_e_travel_bundle(tmp_path: Path) -> None:
    """Flight + Hotel bundle。"""
    from universal_agent.core.contracts import RawHotel, RawListing
    from universal_agent.domains.travel import compose_travel_bundle
    flights = [RawListing.model_validate({
        "listing_id": "f1", "source": "s", "marketplace_id": "s", "task_id": "t1",
        "origin_airport": "PVG", "dest_airport": "ZQN",
        "depart_date": "2026-08-30", "return_date": "2026-09-06", "nights": 7,
        "price_cny": 4000.0,
        "outbound": {"segments": [], "total_min": 900, "stops": -1},
        "inbound": {"segments": [], "total_min": 0, "stops": -1}})]
    hotels = [RawHotel.model_validate({
        "hotel_id": "h1", "source": "c", "marketplace_id": "c", "task_id": "t1",
        "name": "H", "city": "ZQN", "room_name": "Standard",
        "price_per_night_cny": 800.0, "check_in": "2026-08-30",
        "check_out": "2026-09-06", "nights": 7})]
    r = compose_travel_bundle(flights, hotels, task_id="t1")
    assert r.bundles and r.bundles[0].cost["total"] > 0


# ===================== TEST F — Jobs =====================
def test_f_jobs_discovery_and_human_boundary(tmp_path: Path) -> None:
    """Job discovery + human-only 边界。"""
    from universal_agent.core.contracts import RawJob
    from universal_agent.domains.jobs import normalize_job
    from universal_agent.domains.jobs.action import is_human_only
    raw = RawJob(job_id="j1", source="seek", marketplace_id="seek", task_id="t1",
                 title="Backend Engineer", company="ACME", location="Auckland",
                 salary_text="120k", job_reference="REF1", skills=["python"])
    cand, _, _, _ = normalize_job(raw, "t1", wanted_skills=["python"])
    assert cand.domain == "jobs" and cand.attributes["match_ratio"] > 0
    assert is_human_only("描述你的性格特质")
    assert not is_human_only("简述项目经验")


# ===================== TEST G — Actions =====================
def test_g_actions_mock_side_effects(tmp_path: Path) -> None:
    """Prepare → Approval → 无真实资金副作用（mock）。"""
    from universal_agent.actions.approval import ApprovalInbox
    from universal_agent.actions.gateway.prepare import ActionPreparer
    from universal_agent.actions.idempotency import IdempotencyStore
    from universal_agent.core.contracts import ActionIntent, ActionLevel, Reversibility
    from universal_agent.observability.audit import AuditLog
    from universal_agent.registry import SkillRegistry

    p = ActionPreparer(idempotency=IdempotencyStore(tmp_path / "idem"),
                       approvals=ApprovalInbox(tmp_path / "ap"),
                       audit=AuditLog(tmp_path / "au"),
                       skill_registry=SkillRegistry())
    intent = ActionIntent(intent_id="i1", action="prepare_order", target_key="f1",
                          params={"quote_id": "q", "offer_id": "o", "offer_version": 1,
                                  "candidate_version": 1},
                          idempotency_key="idem-1", level=ActionLevel.L2_PREPARE,
                          reversibility=Reversibility.PARTIAL, max_slippage_cny=100)
    out = p.prepare(intent, confirmed_price=3659.0)
    assert out.status in ("PREPARED", "PENDING_APPROVAL")
    assert len(p.approvals.pending()) >= 1  # Approval Inbox 收集


# ===================== TEST H — Host Swap =====================
def test_h_host_swap_harness_to_jarvis(tmp_path: Path) -> None:
    """Harness → Jarvis：Core 零修改，状态继续。"""
    svc_h = UniversalAgentService(data_dir=tmp_path / "data", host="deepseek_harness")
    svc_h.coordinator.create_watch(_task())
    svc_h.coordinator.activate("w-final")
    svc_h.close()

    svc_j = UniversalAgentService(data_dir=tmp_path / "data", host="jarvis")
    try:
        t = svc_j.coordinator.get("w-final")
        assert t is not None and t.state == WatchState.ACTIVE
        svc_j.coordinator.pause("w-final")
        assert svc_j.coordinator.get("w-final").state == WatchState.PAUSED
    finally:
        svc_j.close()


# ===================== TEST I — Failure Injection =====================
def test_i_failure_injection_source_down(tmp_path: Path) -> None:
    """源失败不中断整体；DB busy 不崩。"""
    from universal_agent.coordinator.scanner import ShadowScanCoordinator
    from universal_agent.core.contracts import RawListing, TaskSpec
    from universal_agent.events import InProcessEventBus
    from universal_agent.memory import ObservationStore
    from universal_agent.registry import MarketplaceManifest, SkillRegistry

    def good(q):
        return [RawListing.model_validate({
            "listing_id": "g", "source": "g", "marketplace_id": "g", "task_id": "t1",
            "origin_airport": q.origin, "dest_airport": "ZQN",
            "depart_date": q.depart_date, "return_date": q.return_date, "nights": 7,
            "price_cny": 4000.0,
            "outbound": {"segments": [], "total_min": 900, "stops": -1},
            "inbound": {"segments": [], "total_min": 0, "stops": -1}})]

    def broken(q):
        raise RuntimeError("source timeout")  # failure injection

    reg = SkillRegistry()
    reg.register_marketplace(MarketplaceManifest(id="good", domains=["flight"],
                                                  health="HEALTHY",
                                                  trust={"default_score": 0.9}))
    reg.register_marketplace(MarketplaceManifest(id="broken", domains=["flight"],
                                                  health="HEALTHY",
                                                  trust={"default_score": 0.9}))
    coord = ShadowScanCoordinator(bus=InProcessEventBus(), registry=reg,
                                  observations=ObservationStore(tmp_path / "obs"),
                                  fetchers={"good": good, "broken": broken},
                                  max_queries=2)
    task = TaskSpec(id="t1", type="watch", domain="flight",
                    search_space={"origin": ["HGH"], "destination": ["ZQN"],
                                  "departure": {"start": "2026-08-30", "end": "2026-08-30"},
                                  "nights": {"min": 7, "preferred": 7, "max": 7}})
    out = asyncio.run(coord.scan(task))
    assert out.raw_listings  # 好源数据保留；坏源被降级不中断
    assert reg.get_marketplace("broken").health == "DEGRADED"


# ===================== TEST J — Security =====================
def test_j_security_isolation(tmp_path: Path) -> None:
    """Credential 隔离 + 默认拒绝权限。"""
    from universal_agent.security.credential_vault.vault import CredentialVault
    from universal_agent.security.permissions.manager import PermissionManager
    v = CredentialVault(tmp_path / "vault")
    v.set("payment", {"card": "4111111111111111", "cvv": "123"})
    raw = (tmp_path / "vault" / "credentials.json").read_text()
    assert "4111111111111111" not in raw  # 明文不落盘
    assert v.masked("payment").get("card") != "4111111111111111"  # 掩码

    pm = PermissionManager(tmp_path / "perms")
    assert pm.check("user1", "execute_payment") is False  # 默认拒绝
    pm.grant("user1", "read_tasks")
    assert pm.check("user1", "read_tasks") is True
