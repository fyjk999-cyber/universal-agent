"""Job domain action + answer helpers (§64/§65).

Domain ONLY builds ActionPlans — never executes (RULE 6 / §36).
Job application submission is IRREVERSIBLE (§40) → ActionGateway blocks it
until L3/L4 gates are stable. Answer memory reuses Core MemoryStore.
"""
from __future__ import annotations

from typing import Dict, List

from ...core.contracts import (
    ActionIntent,
    ActionLevel,
    ActionPlan,
    MemoryRecord,
    Reversibility,
    new_id,
)
from ...memory import MemoryStore, Scope


def build_application_plan(task_id: str, job_candidate_id: str,
                           resume_ref: str, cover_letter: str = "",
                           slippage_cny: float = 0.0) -> ActionPlan:
    """Build an Application ActionPlan（§65 PREPARE 到提交前）。

    Level=L1_RECOMMEND（V1 只开放 L0/L1）；reversibility=IRREVERSIBLE，
    因此 ActionGateway 会拒绝执行——这正是设计意图（§40/§56）。
    """
    intent = ActionIntent(
        intent_id=new_id("int"),
        action="submit_application",
        target_key=job_candidate_id,
        params={
            "resume_ref": resume_ref,
            "cover_letter": cover_letter,
        },
        idempotency_key=new_id("idem"),
        level=ActionLevel.L1_RECOMMEND,
        reversibility=Reversibility.IRREVERSIBLE,
        max_slippage_cny=slippage_cny,
        max_slippage_percent=0.0,
    )
    return ActionPlan(
        plan_id=new_id("plan"),
        task_id=task_id,
        target_key=job_candidate_id,
        intents=[intent],
    )


def store_answer_memory(memory: MemoryStore, task_id: str,
                        question: str, answer: str,
                        source: str = "job_prep") -> MemoryRecord:
    """Answer Memory（§64）：TASK scope 保存面试/申请问题的答案草稿。"""
    return memory.put(
        Scope.TASK, key=f"answer::{question[:40]}", value=answer,
        task_id=task_id, kind="answer", source=source,
    )


def store_application_draft(memory: MemoryStore, task_id: str,
                            fields: Dict[str, str]) -> MemoryRecord:
    """保存申请草稿（简历/动机信），TASK scope。"""
    return memory.put(Scope.TASK, key="application_draft", value=fields,
                      task_id=task_id, kind="preference", source="job_prep")


#: HUMAN-ONLY 边界（P13）：这些内容禁止 AI 代答
_HUMAN_ONLY_MARKERS = (
    # personality 测试
    "性格", "人格", "personality", "mbti", "价值观测试",
    # truth 声明
    "确认.*真实", "truth", "属实声明",
    # identity
    "身份证", "护照号", "identity", "出生日期", "社保",
    # 法律敏感
    "犯罪记录", "法律", "legal", "授权", "同意书",
)


def is_human_only(question: str) -> bool:
    """判断问题是否属于 HUMAN-ONLY（AI 禁止代答）。"""
    import re
    q = question.lower()
    for marker in _HUMAN_ONLY_MARKERS:
        if re.search(marker, q):
            return True
    return False
