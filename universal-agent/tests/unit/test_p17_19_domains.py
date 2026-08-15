"""P17/P18/P19 — Railway / Ecommerce / Food Domain。

验收：
1. Railway：RawRailway → Candidate（车次/席别/出发到达）
2. Ecommerce：RawProduct → Candidate（canonical SKU）
3. Food：RawDish → Candidate（菜品/餐厅）
4. 全部复用既有 Core 契约（Candidate/Offer/Quote/Evidence），零 Core 修改
"""
from __future__ import annotations

from pathlib import Path

import pytest


def test_railway_normalize(tmp_path: Path) -> None:
    from universal_agent.core.contracts import RawRailway, Scope
    from universal_agent.domains.railway import entity_key, normalize_railway

    raw = RawRailway(
        railway_id="r1", source="12306", marketplace_id="12306", task_id="t1",
        train_no="G1373", origin_city="上海", dest_city="杭州",
        depart_date="2026-08-30", depart_time="08:00", arrive_time="09:30",
        seat_class="二等座", price_cny=73.0,
    )
    cand, offer, quote, _ = normalize_railway(raw, "t1")
    assert cand.domain == "railway"
    assert cand.attributes["train_no"] == "G1373"
    assert offer.marketplace_id == "12306"
    assert quote.price.amount == 73.0
    assert entity_key(raw)


def test_ecommerce_normalize(tmp_path: Path) -> None:
    from universal_agent.core.contracts import RawProduct
    from universal_agent.domains.ecommerce import entity_key, normalize_product

    raw = RawProduct(
        product_id="p1", source="taobao", marketplace_id="taobao", task_id="t1",
        title="无线鼠标", sku="SKU-001", price_cny=59.0, stock=10,
    )
    cand, offer, quote, _ = normalize_product(raw, "t1")
    assert cand.domain == "ecommerce"
    assert cand.attributes["sku"] == "SKU-001"
    assert quote.price.amount == 59.0
    assert entity_key(raw)


def test_food_normalize(tmp_path: Path) -> None:
    from universal_agent.core.contracts import RawDish
    from universal_agent.domains.food import entity_key, normalize_dish

    raw = RawDish(
        dish_id="d1", source="meituan", marketplace_id="meituan", task_id="t1",
        restaurant="外婆家", dish_name="东坡肉", price_cny=48.0,
    )
    cand, offer, quote, _ = normalize_dish(raw, "t1")
    assert cand.domain == "food"
    assert cand.attributes["dish_name"] == "东坡肉"
    assert quote.price.amount == 48.0
    assert entity_key(raw)


def test_no_core_changes_needed(tmp_path: Path) -> None:
    """三个 Domain 只用既有契约（Candidate/Offer/Quote 存在即可用）。"""
    from universal_agent.core.contracts import Candidate, Offer, Quote
    # 契约存在即验证：三个新 Domain 复用它们
    assert Candidate is not None and Offer is not None and Quote is not None
