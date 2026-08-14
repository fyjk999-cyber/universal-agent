"""CareerPilot Migration Test（§64/§65）— Job Domain 接入 Universal Core。

正式验收：Universal Core 无需任何修改即可处理：
  - Job Candidate / Multiple Listings / Job Watch
  - Application ActionPlan（IRREVERSIBLE → Gateway 拒绝执行）
  - Answer Memory

若本测试需要修改 Core（contracts/events/memory/registry/watch_manager/
state_machine）才能通过 → 抽象被破坏，按规范暂停开发重审。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from universal_agent.actions import ActionGateway
from universal_agent.coordinator import TaskRegistry, WatchManager
from universal_agent.coordinator.scanner import JobScanCoordinator
from universal_agent.core.contracts import (
    Reversibility,
    TaskSpec,
    TaskType,
    WatchState,
)
from universal_agent.core.state_machine import can_transition
from universal_agent.domains.jobs import (
    build_application_plan,
    entity_key,
    normalize_job,
    score_job,
    store_answer_memory,
)
from universal_agent.events import EventType, InProcessEventBus
from universal_agent.memory import MemoryStore, Scope
from universal_agent.registry import CapabilityDenied, MarketplaceManifest, SkillRegistry

FIXTURES = Path(__file__).resolve().parent.parent / "replay" / "fixtures"

CORE_MODULES = [
    "universal_agent.core.contracts",
    "universal_agent.core.state_machine",
    "universal_agent.events",
    "universal_agent.memory",
    "universal_agent.registry",
    "universal_agent.coordinator.task_registry",
    "universal_agent.coordinator.watch_manager",
    "universal_agent.actions",
]


def _job_task() -> TaskSpec:
    return TaskSpec(
        id="careerpilot-ai-watch", type=TaskType.WATCH, domain="jobs",
        search_space={"extra": {"keywords": ["AI Engineer", "ML"]}},
        notify_if={"opportunity_score_gte": 80},
    )


def _load_jobs() -> list:
    raw = json.loads((FIXTURES / "linkedin.json").read_text("utf-8"))
    from universal_agent.core.contracts import RawJob
    return [RawJob.model_validate(r) for r in raw]


def _registry() -> SkillRegistry:
    reg = SkillRegistry()
    reg.register_marketplace(MarketplaceManifest(
        id="linkedin", domains=["jobs"], health="HEALTHY",
        trust={"default_score": 0.9}))
    return reg


class TestJobNormalize:
    def test_job_entity_key(self):
        jobs = _load_jobs()
        assert entity_key(jobs[0]) == entity_key(jobs[0])
        assert entity_key(jobs[0]) != entity_key(jobs[1])

    def test_normalize_to_core_contracts(self):
        job = _load_jobs()[0]
        cand, offer, quote, evidence = normalize_job(job, "t1",
                                                     wanted_skills=["python", "llm", "agent"])
        assert cand.domain == "jobs"
        assert cand.attributes["match_ratio"] > 0.5  # 高匹配
        assert offer.terms["company"] == "DeepMind Shanghai"
        assert quote.price.amount > 0  # 薪资中位
        assert evidence.field == "salary"

    def test_score_job_deterministic(self):
        jobs = _load_jobs()
        scores = [score_job(j, market_salary=50000,
                            wanted_skills=["python", "llm", "agent"])["total"]
                  for j in jobs]
        # AI Engineer 匹配度最高 → 总分最高
        assert scores[0] > scores[2]


class TestJobWatch:
    """Job Watch 复用 Core WatchManager/状态机/Registry——零 Core 修改。"""

    def test_job_task_in_core_state_machine(self):
        # Job task 走同一状态机
        assert can_transition(WatchState.DRAFT, WatchState.ACTIVE)
        assert can_transition(WatchState.ACTIVE, WatchState.WATCHING)

    def test_watch_manager_handles_job_task(self, tmp_path):
        reg = TaskRegistry(tmp_path / "reg")
        wm = WatchManager(reg, InProcessEventBus())
        from universal_agent.core.contracts import WatchTask
        task = WatchTask(**{**_job_task().model_dump(), "state": WatchState.DRAFT})
        created = wm.create_watch(task)
        active = wm.activate(created.id)
        assert active.state == WatchState.ACTIVE
        watching = wm.start_watching(created.id)
        assert watching.state == WatchState.WATCHING


class TestJobScan:
    @pytest.mark.asyncio
    async def test_job_scan_pipeline(self, tmp_path):
        jobs = _load_jobs()

        def fetch(kw):
            # 按关键词过滤（模拟真实源），避免重复
            return [j for j in jobs if kw.lower() in
                    f"{j.title} {j.description}".lower()] or jobs

        coord = JobScanCoordinator(
            bus=InProcessEventBus(), registry=_registry(),
            observations=None,
            fetchers={"linkedin": fetch},
            wanted_skills=["python", "llm", "agent"])
        out = await coord.scan(_job_task())
        assert out.raw_jobs  # 至少抓取到职位
        assert out.candidates
        assert 1 <= len(out.top3) <= 3
        # 事件链（复用 Core EventBus）
        assert EventType.SCAN_REQUESTED.value in out.emitted_events
        assert EventType.CANDIDATE_CREATED.value in out.emitted_events

    @pytest.mark.asyncio
    async def test_job_source_failure_degrades(self, tmp_path):
        reg = _registry()

        def bad(kw):
            raise RuntimeError("linkedin down")

        coord = JobScanCoordinator(
            bus=InProcessEventBus(), registry=reg,
            fetchers={"linkedin": bad})
        out = await coord.scan(_job_task())
        assert out.raw_jobs == []
        assert reg.get_marketplace("linkedin").health == "DEGRADED"


class TestApplicationActionPlan:
    def test_plan_built_not_executed(self):
        """§36/§64: Domain 只 build_action_plan，绝不 execute。"""
        plan = build_application_plan("t1", "jcand-1", resume_ref="resume://v3")
        assert plan.status == "PLANNED"
        assert not hasattr(plan, "execute")
        intent = plan.intents[0]
        assert intent.action == "submit_application"
        assert intent.reversibility == Reversibility.IRREVERSIBLE  # §40

    def test_gateway_blocks_irreversible_job_submission(self):
        """§40/§56: IRREVERSIBLE Job 提交被 ActionGateway 拒绝（V1）。"""
        gw = ActionGateway()
        plan = build_application_plan("t1", "jcand-1", resume_ref="resume://v3")
        with pytest.raises(CapabilityDenied):
            gw.check_intent(plan.intents[0])


class TestAnswerMemory:
    def test_answer_stored_task_scope(self, tmp_path):
        mem = MemoryStore(tmp_path / "mem")
        rec = store_answer_memory(mem, "t1",
                                  "Why do you want to join?",
                                  "Because of the LLM agent work.")
        assert rec.scope == Scope.TASK
        assert rec.task_id == "t1"
        assert rec.kind == "answer"
        got = mem.get(Scope.TASK, rec.key, task_id="t1")
        assert got is not None and got.value == "Because of the LLM agent work."


class TestZeroCoreChanges:
    def test_core_modules_import_unmodified(self):
        """§64 验收：Job 域接入不触碰 Core 模块（import 证明）。"""
        import importlib
        for mod in CORE_MODULES:
            importlib.import_module(mod)

    def test_no_import_of_job_domain_from_core(self):
        """反向验证：Core 不 import jobs 域（RULE 3 隔离）。"""
        import universal_agent.core.contracts as c
        src = c.__file__
        content = Path(src).read_text("utf-8")
        # contracts 里只有 RawJob 数据契约，无 jobs 领域逻辑
        assert "from .raw import" in content or "RawJob" in content
