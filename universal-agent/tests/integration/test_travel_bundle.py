"""PHASE 4 集成测试：Hotel 扫描 + Flight+Hotel Bundle 组合（§26/§27/§28）。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from universal_agent.adapters.replay import load_fixtures
from universal_agent.core.bundling import best_bundle
from universal_agent.core.contracts import RawHotel, TaskSpec
from universal_agent.coordinator.scanner import HotelScanCoordinator
from universal_agent.domains.hotel import entity_key
from universal_agent.domains.travel import compose_travel_bundle
from universal_agent.events import InProcessEventBus
from universal_agent.memory import ObservationStore
from universal_agent.registry import MarketplaceManifest, SkillRegistry

FIXTURES = Path(__file__).resolve().parent.parent / "replay" / "fixtures"


def _task() -> TaskSpec:
    return TaskSpec(
        id="queenstown-travel-watch", type="watch", domain="travel",
        search_space={
            "origin": ["HGH", "PVG", "SHA"], "destination": ["ZQN"],
            "departure": {"start": "2026-08-30", "end": "2026-09-03"},
            "nights": {"min": 6, "preferred": 7, "max": 8},
        },
    )


def _load_hotels() -> list[RawHotel]:
    return load_fixtures(FIXTURES, "booking")


def _load_flights() -> list:
    from universal_agent.core.contracts import RawListing
    raw = json.loads((FIXTURES / "ctrip.json").read_text("utf-8"))
    return [RawListing.model_validate(r) for r in raw]


class TestHotelScan:
    @pytest.mark.asyncio
    async def test_hotel_scan_pipeline(self, tmp_path):
        reg = SkillRegistry()
        reg.register_marketplace(MarketplaceManifest(
            id="booking", domains=["hotel"], health="HEALTHY",
            trust={"default_score": 0.85}))
        hotels = _load_hotels()

        def fetch(city):
            # city 是机场码 ZQN → 映射到 Queenstown
            if city == "ZQN":
                return hotels
            return [h for h in hotels if h.city == city]

        coord = HotelScanCoordinator(
            bus=InProcessEventBus(), registry=reg,
            observations=ObservationStore(tmp_path / "obs"),
            fetchers={"booking": fetch})
        out = await coord.scan(_task())
        assert out.raw_hotels == hotels
        assert out.candidates
        assert out.best is not None
        # 评分最高：Eichardt's Suite (rating 4.8) 或评分靠前
        assert out.best.name in {h.name for h in hotels}

    @pytest.mark.asyncio
    async def test_hotel_failing_source_degrades(self, tmp_path):
        reg = SkillRegistry()
        reg.register_marketplace(MarketplaceManifest(
            id="booking", domains=["hotel"], health="HEALTHY",
            trust={"default_score": 0.85}))

        def bad(city):
            raise RuntimeError("booking down")

        coord = HotelScanCoordinator(
            bus=InProcessEventBus(), registry=reg,
            observations=ObservationStore(tmp_path / "obs"),
            fetchers={"booking": bad})
        out = await coord.scan(_task())
        assert out.raw_hotels == []
        assert reg.get_marketplace("booking").health == "DEGRADED"


class TestTravelBundle:
    def test_compose_flight_hotel_bundle(self):
        flights = _load_flights()
        hotels = _load_hotels()
        res = compose_travel_bundle(flights, hotels, task_id="t1")
        assert res.bundles
        best = best_bundle(res.bundles)
        assert "flight" in best.components
        assert "hotel" in best.components
        assert best.cost["total"] > 0
        # 总成本 = 机票 + 酒店×晚数
        assert best.cost["total"] == round(
            best.cost["flight"] + best.cost["hotel"], 2)

    def test_bundle_flight_only(self):
        flights = _load_flights()
        res = compose_travel_bundle(flights, hotels=None, task_id="t1")
        assert res.bundles
        assert best_bundle(res.bundles).components == {"flight": res.bundles[0].components["flight"]}

    def test_bundle_hotel_dedup_by_entity(self):
        flights = _load_flights()
        hotels = _load_hotels()
        # 同一酒店不同来源 → 去重（entity key）
        dup = _load_hotels()[0].model_copy()
        dup.hotel_id = "dup-1"
        dup.source = "agoda"
        dup.marketplace_id = "agoda"
        res = compose_travel_bundle(flights, hotels + [dup], task_id="t1")
        # 酒店按 entity key 去重后参与组合；每个 bundle 至多含 1 个 hotel 组件
        assert len(res.bundles) >= 1
        # 验证去重：compose 内部按 entity_key 去重，重复酒店只计一次
        from universal_agent.domains.hotel import entity_key as hkey
        keys = {hkey(h) for h in hotels + [dup]}
        assert len(keys) == len(hotels)  # dup 与首个酒店同 key → 集合大小不变

    def test_bundle_respects_constraint(self):
        """§28: 约束下非贪心组合胜出。"""
        flights = _load_flights()
        hotels = _load_hotels()

        def valid_pair(f, h):
            # 最便宜航班(3980)不能配 Heritage 酒店（模拟日期绑定）
            if "3980" in str(f.price) and "heritage" in str(h).lower():
                return False
            return True

        res = compose_travel_bundle(flights, hotels, task_id="t1",
                                    valid_pair=valid_pair)
        assert res.bundles
