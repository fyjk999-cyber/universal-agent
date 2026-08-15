"""SkillProtocol（P5）— 平台能力接口。

Domain = 领域知识；Skill = 平台能力；Adapter = 通信机制。

Skill 提供查询能力：search/detail/verify/availability/prepare_action/health_check。
高危 execute_action 不在本接口上（只经 ActionGateway → Policy → Approval）。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class SkillProtocol(ABC):
    """一个平台 skill 的标准接口。"""

    skill_id: str = ""
    domains: List[str] = []

    @abstractmethod
    def search(self, query: Dict[str, Any]) -> List[Dict[str, Any]]:
        """按查询条件返回候选列表（raw）。"""

    @abstractmethod
    def detail(self, item_key: str) -> Dict[str, Any]:
        """获取单个候选的详情（STRUCTURED）。"""

    @abstractmethod
    def verify(self, item_key: str) -> Dict[str, Any]:
        """验证一个候选/报价的真实性与时效。"""

    @abstractmethod
    def availability(self, item_key: str) -> Dict[str, Any]:
        """查询库存/可订状态。"""

    @abstractmethod
    def prepare_action(self, item_key: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """L2 PREPARE：推进到确认页/提交前，不 commit。"""

    @abstractmethod
    def health_check(self) -> Dict[str, Any]:
        """返回 {status: HEALTHY|DEGRADED|..., latency_ms, last_success}。"""
