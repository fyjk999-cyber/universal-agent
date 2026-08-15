"""P8 — Flight Live Vertical Slice：Skyscanner 作为完整 SkillProtocol。

验收：
1. SkyscannerAdapter 实现 SkillProtocol（search/detail/verify/availability/
   prepare_action/health_check）
2. search 产出 RawListing 且 fail-closed（不完整 → PARTIAL，不伪造）
3. health_check 反映 Source Health
4. detail/verify 对不存在的 item 返回安全结果（不崩）
5. prepare_action 返回 NOT_READY（L2 未实现时不得 commit）
"""
from __future__ import annotations

from pathlib import Path

import pytest

from universal_agent.adapters.skyscanner import SkyscannerAdapter, SkyscannerConfig
from universal_agent.registry.skills.protocol import SkillProtocol


@pytest.fixture()
def adapter(tmp_path: Path) -> SkyscannerAdapter:
    return SkyscannerAdapter(config=SkyscannerConfig(request_delay_sec=0))


def test_implements_skill_protocol(adapter) -> None:
    assert isinstance(adapter, SkillProtocol)


def test_protocol_methods_present(adapter) -> None:
    for m in ("search", "detail", "verify", "availability",
              "prepare_action", "health_check"):
        assert callable(getattr(adapter, m, None)), f"missing {m}"


def test_health_check_shape(adapter) -> None:
    h = adapter.health_check()
    assert "status" in h
    assert h["status"] in ("HEALTHY", "DEGRADED", "UNAVAILABLE", "UNKNOWN")


def test_detail_unknown_item_returns_empty(adapter) -> None:
    """未知 item → 空结构（不崩，fail-closed）。"""
    d = adapter.detail("nonexistent-item")
    assert isinstance(d, dict)


def test_verify_unknown_item_returns_unverified(adapter) -> None:
    v = adapter.verify("nonexistent-item")
    assert isinstance(v, dict)
    # 未知不可验证 → 不假装 verified
    assert v.get("verified", False) is False


def test_availability_unknown_item(adapter) -> None:
    a = adapter.availability("nonexistent-item")
    assert isinstance(a, dict)


def test_prepare_action_no_commit(adapter) -> None:
    """L2 PREPARE 未实现 → 明确 NOT_READY（绝不 commit）。"""
    r = adapter.prepare_action("item-1", {"passenger": 1})
    assert r.get("status") == "NOT_READY" or "error" in r


def test_search_fail_closed_partial(adapter) -> None:
    """search 对未知/无效查询安全返回空（不抛）。"""
    from universal_agent.coordinator.query_planner import FlightQuery
    q = FlightQuery(origin="ZZZ", destination="YYY", depart_date="2026-08-30",
                    return_date="2026-09-06", nights=7)
    # 不联网时（real_chrome 不可用/网络失败）→ 返回空列表，不抛致命错误
    result = adapter.search({"origin": q.origin, "dest": q.destination})
    assert isinstance(result, list)
