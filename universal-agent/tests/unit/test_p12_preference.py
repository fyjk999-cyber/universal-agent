"""P12 — Preference Learning：从 Decision Memory 学习，versioned/explainable/reversible。

验收：
1. 从决策历史学习价格敏感度/时间敏感度/平台偏好
2. 偏好 versioned（每次更新版本递增）
3. 可解释（learning 带 reason/evidence）
4. 可逆（可回滚到前一版本）
5. 绝不改变 Policy（Policy 是 immutable 的）
"""
from __future__ import annotations

from pathlib import Path

import pytest

from universal_agent.memory.domains import MemoryDomains
from universal_agent.memory.sqlite_store import SqliteMemoryStore
from universal_agent.persistence import Database


@pytest.fixture()
def dom(tmp_path: Path) -> MemoryDomains:
    db = Database(tmp_path / "ua.db")
    return MemoryDomains(SqliteMemoryStore(db))


@pytest.fixture()
def learner(dom):
    from universal_agent.memory.preferences.learner import PreferenceLearner
    return PreferenceLearner(dom)


def _decision(price: float, accepted: bool, platform: str = "ctrip") -> dict:
    return {"price": price, "accepted": accepted, "platform": platform}


def test_learn_price_sensitivity_from_decisions(learner) -> None:
    """多次接受高价 → 价格敏感度下降（更愿意花钱）。"""
    for p in (4000, 4200, 4500, 4800):
        learner.observe_decision("t1", _decision(p, accepted=True))
    pref = learner.price_sensitivity(user_id="u1")
    assert pref is not None
    assert 0.0 <= pref.value["sensitivity"] <= 1.0
    assert pref.kind == "preference"


def test_preference_versioned(learner) -> None:
    """偏好每次学习版本递增。"""
    learner.observe_decision("t1", _decision(4000, True))
    v1 = learner.price_sensitivity(user_id="u1").version
    learner.observe_decision("t2", _decision(5000, True))
    v2 = learner.price_sensitivity(user_id="u1").version
    assert v2 > v1


def test_preference_explainable(learner) -> None:
    """学习记录带 reason/evidence（可解释）。"""
    learner.observe_decision("t1", _decision(4200, True, platform="ctrip"))
    learner.observe_decision("t2", _decision(4200, True, platform="ctrip"))
    pref = learner.platform_preference(user_id="u1")
    assert pref is not None
    assert "evidence" in pref.value or pref.source  # 至少一个解释载体


def test_preference_reversible(learner) -> None:
    """可逆：回滚产生 rolled_back 标记（低置信，可被后续学习覆盖）。"""
    learner.observe_decision("t1", _decision(4000, True))
    learner.observe_decision("t2", _decision(6000, True))
    rolled = learner.rollback("u1", kind="preference")
    assert rolled is not None
    assert rolled.value.get("rolled_back") is True
    assert rolled.confidence is not None and rolled.confidence < 0.5


def test_learning_never_mutates_policy(learner, dom) -> None:
    """学习绝不改变 Policy（Policy 独立于偏好，immutable）。"""
    dom.set_policy("max_payment", 5000)
    for p in (4000, 4500):
        learner.observe_decision("t1", _decision(p, True))
    pol = dom.get_policy("max_payment")
    assert pol is not None and pol.value == 5000  # 未变
