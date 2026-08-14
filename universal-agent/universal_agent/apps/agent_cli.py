"""Universal Agent 综合 CLI — 多域一站式入口.

覆盖全部 Phase 能力：
  --domain flight   Flight Shadow Scan（§61/§62）
  --domain hotel    Hotel 扫描（§63）
  --domain jobs     Job 扫描（§64）
  --domain bundle   Flight+Hotel Bundle 组合（§27/§28）
  --domain prepare  Action PREPARE 演示（§65）
  --domain execute  受控执行演示（§66，默认 DENY）

用法示例:
  python -m universal_agent.apps.agent_cli --domain flight
  python -m universal_agent.apps.agent_cli --domain bundle
  python -m universal_agent.apps.agent_cli --domain jobs
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent.parent


def _registry() -> "SkillRegistry":
    from universal_agent.registry import MarketplaceManifest, SkillRegistry
    reg = SkillRegistry()
    specs = [
        ("ctrip", "flight", 0.90), ("fliggy", "flight", 0.85),
        ("booking", "hotel", 0.85), ("linkedin", "jobs", 0.90),
    ]
    for mid, dom, trust in specs:
        reg.register_marketplace(MarketplaceManifest(
            id=mid, domains=[dom], health="HEALTHY",
            capabilities={"search": True}, trust={"default_score": trust}))
    return reg


def _fixtures() -> Path:
    return BASE / "tests" / "replay" / "fixtures"


async def _flight() -> None:
    from universal_agent.adapters.replay import make_fetchers
    from universal_agent.coordinator.scanner import ShadowScanCoordinator
    from universal_agent.coordinator.task_registry import load_task_spec
    from universal_agent.events import InProcessEventBus
    from universal_agent.memory import ObservationStore
    task = load_task_spec(BASE / "tasks" / "queenstown-travel-watch.yaml")
    coord = ShadowScanCoordinator(
        bus=InProcessEventBus(), registry=_registry(),
        observations=ObservationStore(Path("/tmp/ua-obs")),
        fetchers=make_fetchers(_fixtures(), ["ctrip", "fliggy"]))
    out = await coord.scan(task)
    print("== Flight Top5 ==")
    for i, r in enumerate(out.top5, 1):
        print(f"  #{i} {r.origin_airport}→{r.dest_airport} ¥{r.price_cny:.0f}")
    print(f"  [机会] score={out.opportunity.total_score if out.opportunity else '-'}")


async def _hotel() -> None:
    from universal_agent.adapters.replay import load_fixtures
    from universal_agent.coordinator.scanner import HotelScanCoordinator
    from universal_agent.core.contracts import TaskSpec, TaskType
    from universal_agent.events import InProcessEventBus
    hotels = load_fixtures(_fixtures(), "booking")
    task = TaskSpec(id="q-hotels", type=TaskType.WATCH, domain="travel",
                    search_space={"destination": ["ZQN"]})
    coord = HotelScanCoordinator(
        bus=InProcessEventBus(), registry=_registry(),
        fetchers={"booking": lambda city: hotels})
    out = await coord.scan(task)
    print("== Hotel 扫描 ==")
    print(f"  候选 {len(out.candidates)} 个; 最佳: {out.best.name} ¥{out.best.price_per_night_cny}/晚"
          if out.best else "  无结果")


async def _jobs() -> None:
    from universal_agent.adapters.replay import load_fixtures
    from universal_agent.coordinator.scanner import JobScanCoordinator
    from universal_agent.core.contracts import TaskSpec, TaskType
    from universal_agent.events import InProcessEventBus
    jobs = load_fixtures(_fixtures(), "linkedin")
    task = TaskSpec(id="careerpilot", type=TaskType.WATCH, domain="jobs",
                    search_space={"extra": {"keywords": ["AI"]}})
    coord = JobScanCoordinator(
        bus=InProcessEventBus(), registry=_registry(),
        fetchers={"linkedin": lambda kw: jobs},
        wanted_skills=["python", "llm", "agent"])
    out = await coord.scan(task)
    print("== Job Top3 ==")
    for i, j in enumerate(out.top3, 1):
        print(f"  #{i} {j.title} @ {j.company}")


def _bundle() -> None:
    from universal_agent.adapters.replay import load_fixtures
    from universal_agent.core.bundling import best_bundle
    from universal_agent.domains.travel import compose_travel_bundle
    flights = load_fixtures(_fixtures(), "ctrip")
    hotels = load_fixtures(_fixtures(), "booking")
    res = compose_travel_bundle(flights, hotels, task_id="t1")
    best = best_bundle(res.bundles)
    print("== Flight+Hotel Bundle ==")
    print(f"  组合 {len(res.bundles)} 个; 最优 total=¥{best.cost['total']:.0f} "
          f"(flight ¥{best.cost['flight']:.0f} + hotel ¥{best.cost['hotel']:.0f})")


def _prepare() -> None:
    import tempfile
    from universal_agent.actions import ActionPreparer, ApprovalInbox, IdempotencyStore
    from universal_agent.core.contracts import ActionIntent, ActionLevel, Reversibility
    from universal_agent.observability.audit import AuditLog
    d = Path(tempfile.mkdtemp())
    prep = ActionPreparer(
        idempotency=IdempotencyStore(d / "idem"),
        approvals=ApprovalInbox(d / "appr"), audit=AuditLog(d / "audit"))
    intent = ActionIntent(
        intent_id="i1", action="prepare_order", target_key="cand-1",
        idempotency_key="demo-prepare-1", level=ActionLevel.L2_PREPARE,
        reversibility=Reversibility.TIME_LIMITED, max_slippage_cny=100)
    out = prep.prepare(intent, confirmed_price=4380)
    print("== PREPARE（§65 只到确认页，不 Commit）==")
    print(f"  status={out.status} 审批={out.approval['approval_id'][:8]} "
          f"({out.approval['status']}) audit={out.audit_ref}")


def _execute() -> None:
    import tempfile
    from universal_agent.actions import (
        ApprovalInbox, ControlledExecutor, IdempotencyStore, KillSwitch, PolicyEngine)
    from universal_agent.core.contracts import ActionIntent, ActionLevel, Reversibility
    from universal_agent.observability.audit import AuditLog
    d = Path(tempfile.mkdtemp())
    policy = PolicyEngine(policy_path=BASE / "tasks" / "policy.json")
    ex = ControlledExecutor(
        killswitch=KillSwitch(d / "ks.json"), policy=policy,
        idempotency=IdempotencyStore(d / "idem"),
        approvals=ApprovalInbox(d / "appr"), audit=AuditLog(d / "audit"))
    intent = ActionIntent(
        intent_id="x1", action="execute_order", target_key="c1",
        idempotency_key="demo-exec-1", level=ActionLevel.L4_EXECUTE,
        reversibility=Reversibility.FULL, max_slippage_cny=100)
    out = ex.execute(intent, confirmed_price=4380)
    print("== 受控执行（§66，policy 默认 DENY）==")
    print(f"  status={out.status}  detail={out.detail}")


async def _run(domain: str) -> None:
    handlers = {
        "flight": _flight, "hotel": _hotel, "jobs": _jobs,
        "bundle": lambda: _bundle(), "prepare": lambda: _prepare(),
        "execute": lambda: _execute(),
    }
    fn = handlers.get(domain)
    if fn is None:
        print(f"未知 domain: {domain}；可选: {', '.join(handlers)}")
        sys.exit(1)
    if domain in ("flight", "hotel", "jobs"):
        await fn()
    else:
        fn()


def main() -> None:
    parser = argparse.ArgumentParser(description="Universal Agent 综合 CLI")
    parser.add_argument("--domain", default="flight",
                        help="flight|hotel|jobs|bundle|prepare|execute")
    args = parser.parse_args()
    asyncio.run(_run(args.domain))


if __name__ == "__main__":
    main()
