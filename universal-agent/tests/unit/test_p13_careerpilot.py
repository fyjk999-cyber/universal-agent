"""P13 — CareerPilot Live：Jobs 第二 Domain 验证通用性。

验收：
1. JobSkillProtocol 通用接口（官方/LinkedIn/SEEK 共用）
2. Answer Memory 复用（用户确认过的答案复用，不重复问）
3. Human-only 边界：personality/truth/identity/法律敏感 → 禁止代答
4. 不修改 Core（Job domain 只用既有 Core 设施）
"""
from __future__ import annotations

from pathlib import Path

import pytest


def test_job_skill_protocol_interface() -> None:
    """JobSkillProtocol 定义搜索/详情/验证。"""
    from universal_agent.domains.jobs.protocol import JobSkillProtocol
    for m in ("search", "detail", "health_check"):
        assert hasattr(JobSkillProtocol, m), f"missing {m}"


def test_answer_memory_reuse(tmp_path: Path) -> None:
    """Answer Memory 复用：存答案 → 同 key 可复用。"""
    from universal_agent.core.contracts import Scope
    from universal_agent.domains.jobs.action import store_answer_memory
    from universal_agent.memory import MemoryStore

    mem = MemoryStore(tmp_path / "mem")
    rec = store_answer_memory(mem, "job-1", "期望薪资？", "30k")
    assert rec.kind == "answer"
    got = mem.get(Scope.TASK, rec.key, task_id="job-1")
    assert got is not None and got.value == "30k"


def test_human_only_questions_blocked() -> None:
    """Human-only 边界：敏感问题禁止代答。"""
    from universal_agent.domains.jobs.action import is_human_only
    assert is_human_only("请描述你的性格特质") is True     # personality
    assert is_human_only("请确认这是你的真实学历") is True  # truth
    assert is_human_only("你的身份证号是？") is True        # identity
    assert is_human_only("简述你的项目经验") is False       # 正常问题可答


def test_job_domain_reuses_core(tmp_path: Path) -> None:
    """Job scan 用既有 Core 设施（不新增依赖）。"""
    from universal_agent.coordinator.scanner.job import JobScanCoordinator
    from universal_agent.events import InProcessEventBus
    from universal_agent.memory import ObservationStore
    from universal_agent.registry import SkillRegistry

    coord = JobScanCoordinator(
        bus=InProcessEventBus(), registry=SkillRegistry(),
        observations=ObservationStore(tmp_path / "obs"),
        fetchers={})
    assert coord is not None
