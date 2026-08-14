"""Policy Engine（§35/§36/§66）— 决定哪些动作在什么条件下可执行.

与 ActionGateway 的 capability 强制不同，Policy 是业务层规则：
  - 允许的 action / 级别上限
  - 单笔金额上限
  - 需要审批的动作
  - 禁止的动作（黑名单）

Policy 只能由人配置（RULE 9：偏好学习不可修改安全政策）。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("ua.actions.policy")


class PolicyViolation(RuntimeError):
    pass


@dataclass
class PolicyRule:
    action: str
    level: str = "L4_EXECUTE"      # 该动作允许的最高级别
    max_amount_cny: float = 0.0    # 0 = 不限
    requires_approval: bool = True
    allowed: bool = True           # 黑名单用 False
    note: str = ""


class PolicyEngine:
    """数据驱动策略引擎：JSON 文件为策略真相源。

    默认策略（不可被程序修改）：
      - 所有真实副作用动作默认 DENY（需要显式 policy 放行）
      - 金额上限、审批要求、黑名单
    """

    def __init__(self, policy_path: Optional[Path] = None,
                 default: Optional[Dict[str, Any]] = None) -> None:
        self.policy_path = policy_path
        self.rules: Dict[str, PolicyRule] = {}
        self.default_deny = True
        if policy_path is not None and policy_path.exists():
            self._load(policy_path)
        elif default is not None:
            self._load_from_dict(default)

    def _load(self, path: Path) -> None:
        try:
            data = json.loads(path.read_text("utf-8"))
            self._load_from_dict(data)
        except Exception as exc:  # noqa: BLE001
            log.warning("policy file invalid, using defaults: %s", exc)

    def _load_from_dict(self, data: Dict[str, Any]) -> None:
        self.default_deny = data.get("default_deny", True)
        for r in data.get("rules", []):
            self.rules[r["action"]] = PolicyRule(**r)

    def check(self, *, action: str, level: str,
              amount_cny: Optional[float] = None) -> PolicyRule:
        """检查 action 是否允许在该级别执行。违反 → PolicyViolation。"""
        rule = self.rules.get(action)
        if rule is None:
            if self.default_deny:
                raise PolicyViolation(f"action '{action}' not permitted (default deny)")
            rule = PolicyRule(action=action, allowed=True)
        if not rule.allowed:
            raise PolicyViolation(f"action '{action}' is blacklisted")
        # 级别上限
        from ...core.contracts import ActionLevel
        rank = {"L0_SCAN": 0, "L1_RECOMMEND": 1, "L2_PREPARE": 2,
                "L3_CONFIRM": 3, "L4_EXECUTE": 4}
        if rank.get(level, 99) > rank.get(rule.level, 0):
            raise PolicyViolation(
                f"action '{action}' max level {rule.level}, requested {level}")
        # 金额上限
        if rule.max_amount_cny > 0 and amount_cny is not None \
                and amount_cny > rule.max_amount_cny:
            raise PolicyViolation(
                f"amount ¥{amount_cny:.0f} exceeds policy max ¥{rule.max_amount_cny:.0f}")
        return rule

    def requires_approval(self, action: str) -> bool:
        rule = self.rules.get(action)
        if rule is None:
            return self.default_deny
        return rule.requires_approval

    def add_rule(self, rule: PolicyRule) -> None:
        """运行时添加规则（供测试/演示；生产策略来自文件，人不经代码改）。"""
        self.rules[rule.action] = rule

    def as_dict(self) -> Dict[str, Any]:
        return {"default_deny": self.default_deny,
                "rules": [r.__dict__ for r in self.rules.values()]}
