"""CapabilityResolver（P5）— 按 domain/capability/health/cost/trust/risk 选 skill。

评分：
  1. 必须匹配 domain + capability（硬条件）
  2. health：HEALTHY 首选；DEGRADED 次之；UNAVAILABLE/AUTH_REQUIRED/RATE_LIMITED 排除
  3. 同级 health：trust 高优先；trust 同级 cost 低优先
  4. 无满足 → NoSkillAvailable（fail-closed，不静默降级）
"""
from __future__ import annotations

from typing import Optional

from ..registry import SkillRegistry

_HEALTH_ORDER = {"HEALTHY": 3, "DEGRADED": 2, "UNKNOWN": 1,
                 "AUTH_REQUIRED": 0, "RATE_LIMITED": 0, "UNAVAILABLE": 0}


class NoSkillAvailable(RuntimeError):
    pass


class CapabilityResolver:
    def __init__(self, registry: SkillRegistry) -> None:
        self.registry = registry

    def resolve(self, domain: str, capability: str) -> str:
        """返回最佳 skill_id；无可用 → NoSkillAvailable。"""
        best: Optional[tuple] = None  # (-health_rank, -trust, cost, skill_id)
        best_id: Optional[str] = None
        for m in self.registry.list_skills(domain=domain):
            if not m.capabilities.get(capability, False):
                continue
            rank = _HEALTH_ORDER.get(m.health, 0)
            if rank <= 0:
                continue  # UNAVAILABLE/AUTH_REQUIRED/RATE_LIMITED 排除
            # 越小越优：health rank 高 → -rank 小；trust 高 → -trust 小；cost 低 → cost 小
            score = (-rank, -m.trust, m.cost)
            if best is None or score < best:
                best = score
                best_id = m.skill_id
        if best_id is None:
            raise NoSkillAvailable(
                f"no skill for domain={domain} capability={capability}")
        return best_id
