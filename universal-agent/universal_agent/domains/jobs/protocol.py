"""JobSkillProtocol（P13）— 岗位平台通用接口。

官方 Careers / LinkedIn / SEEK 等实现此接口；Core 只依赖协议。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List


class JobSkillProtocol(ABC):
    """一个岗位平台的标准接口。"""

    skill_id: str = ""

    @abstractmethod
    def search(self, query: Dict[str, Any]) -> List[Dict[str, Any]]:
        """按关键词/地点/薪资返回岗位列表。"""

    @abstractmethod
    def detail(self, job_reference: str) -> Dict[str, Any]:
        """岗位详情。"""

    @abstractmethod
    def health_check(self) -> Dict[str, Any]:
        """{status, latency_ms}。"""
