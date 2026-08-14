"""Compensation（§37/§40）— 事务性执行补偿。

一个动作 = 一系列补偿步骤。若执行/验证失败，按逆序执行 compensation，
尽力把系统恢复到一致状态（reversibility 决定可补偿程度：
FULL=完全撤销 / PARTIAL=部分 / TIME_LIMITED=限时 / IRREVERSIBLE=不可补）。

设计：补偿步骤由 Skill/Adapter 提供；本模块只做编排 + 记录。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from ...core.contracts import Reversibility
from ...observability.audit import AuditLog

log = logging.getLogger("ua.actions.compensation")


@dataclass
class CompensationStep:
    name: str
    revert: Callable[[], None]  # 撤销此步骤副作用
    compensatable: bool = True


@dataclass
class CompensationResult:
    status: str  # NOOP | COMPENSATED | PARTIAL | FAILED
    executed: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


class CompensationManager:
    """逆序执行补偿步骤；记录到 audit。"""

    def __init__(self, audit: Optional[AuditLog] = None) -> None:
        self.audit = audit

    def compensate(self, steps: List[CompensationStep],
                   failure_stage: str,
                   reversibility: Reversibility,
                   task_id: Optional[str] = None) -> CompensationResult:
        """逆序尝试撤销已完成步骤。IRREVERSIBLE → 不做补偿，记录。"""
        if reversibility == Reversibility.IRREVERSIBLE:
            self._record(task_id, failure_stage, "NOOP",
                         "IRREVERSIBLE — no compensation possible")
            return CompensationResult(status="NOOP")

        executed: List[str] = []
        errors: List[str] = []
        for step in reversed(steps):
            if not step.compensatable:
                continue
            try:
                step.revert()
                executed.append(step.name)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{step.name}: {exc}")
                log.error("compensation step %s failed: %s", step.name, exc)

        status = "COMPENSATED" if not errors else "PARTIAL"
        self._record(task_id, failure_stage, status,
                     f"compensated={executed} errors={errors}")
        return CompensationResult(status=status, executed=executed, errors=errors)

    def _record(self, task_id, stage, status, detail) -> None:
        if self.audit is not None:
            self.audit.record(
                actor="compensation_manager", action=f"COMPENSATE::{stage}",
                reason="rollback after failed execution",
                based_on={"stage": stage},
                approved=None,
                result={"status": status, "detail": detail},
                task_id=task_id)
