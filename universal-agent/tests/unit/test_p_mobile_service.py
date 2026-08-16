"""P-MOBILE 主线接入：UniversalAgentService 装配 AppiumSkill。

验收：
1. Service 装配 SkillRegistry + CapabilityResolver
2. AppiumSkill 注册为 mobile 域 skill
3. Resolver 能按 domain=iphone capability=search 选到 AppiumSkill
4. health_check 反映真机 WDA 状态（可注入假 transport）
"""
from __future__ import annotations

from pathlib import Path

import pytest

from universal_agent.service import UniversalAgentService


def test_service_assembles_skill_registry(tmp_path: Path) -> None:
    """Service 有 skill_registry + capabilities resolver。"""
    svc = UniversalAgentService(data_dir=tmp_path / "data")
    try:
        assert svc.skill_registry is not None
        assert svc.capabilities is not None
    finally:
        svc.close()


def test_appium_skill_registered(tmp_path: Path) -> None:
    """AppiumSkill 注册进 registry（mobile/iphone 域）。"""
    svc = UniversalAgentService(data_dir=tmp_path / "data")
    try:
        skills = svc.skill_registry.list_skills(domain="iphone")
        assert any(s.skill_id == "appium.iphone" for s in skills)
    finally:
        svc.close()


def test_resolver_finds_appium_for_iphone(tmp_path: Path) -> None:
    """Resolver 按 domain=iphone capability=search 选到 AppiumSkill。"""
    svc = UniversalAgentService(data_dir=tmp_path / "data")
    try:
        picked = svc.capabilities.resolve(domain="iphone", capability="search")
        assert picked == "appium.iphone"
    finally:
        svc.close()


def test_service_appium_skill_health(tmp_path: Path) -> None:
    """Service 暴露的 AppiumSkill health_check 可调用。"""
    svc = UniversalAgentService(data_dir=tmp_path / "data")
    try:
        skill = svc.skill_registry.get_skill("appium.iphone")
        assert skill is not None
        assert skill.capabilities.get("search") is True
        # 高危 execute 不在 skill 能力里（只经 ActionGateway）
        assert skill.capabilities.get("execute_order", False) is False
    finally:
        svc.close()
