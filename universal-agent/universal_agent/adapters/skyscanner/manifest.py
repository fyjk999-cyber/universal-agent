"""Skyscanner flight skill manifest (RULE 4: skill declares platform capability).

§23 要求每个 Skill 显式声明能力。Skyscanner 仅提供 search / price_verify
（公开搜索结果），不提供 prepare_order / execute_order。
"""
from __future__ import annotations

from universal_agent.core.contracts import MarketplaceManifest, SkillManifest


def skyscanner_skill_manifest() -> SkillManifest:
    return SkillManifest(
        skill_id="skyscanner.flight",
        version="0.1.0",
        domains=["flight"],
        capabilities={
            "search": True,
            "detail": False,        # 详情页未实现（仅列表价格）
            "availability": False,
            "price_verify": True,   # 真实抓取价可做 Tier2 交叉验证
            "prepare_order": False,
            "execute_order": False,
        },
        transport=["browser"],
        risk={"execution": "none"},
        description="Skyscanner 公开搜索结果（浏览器渲染，尊重 robots Crawl-Delay:2）",
    )


def skyscanner_marketplace_manifest() -> MarketplaceManifest:
    return MarketplaceManifest(
        id="skyscanner",
        domains=["flight"],
        capabilities={"search": True, "price_verify": True},
        trust={"default_score": 0.8},
        health="HEALTHY",
    )
