"""PHASE 4b 测试：实时汇率 / 并发抓取 / Tier3 官方源验证骨架。"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from universal_agent.adapters.fx import FxService
from universal_agent.adapters.official import (
    NoOpOfficialVerifier,
    OfficialSourceRegistry,
    StubOfficialVerifier,
)
from universal_agent.adapters.skyscanner import SkyscannerAdapter, SkyscannerConfig
from universal_agent.core.contracts import RawListing
from universal_agent.coordinator.query_planner import FlightQuery


class TestFxService:
    def test_uses_cache_when_fresh(self, tmp_path):
        cache = tmp_path / "fx.json"
        cache.write_text(json.dumps({
            "fetched_at": time.time(), "rates": {"GBP": 0.11, "USD": 0.15},
        }), "utf-8")
        fx = FxService(cache_path=cache)
        assert fx.convert(1100, "GBP") == pytest.approx(10000.0, rel=0.1)

    def test_offline_fallback(self, tmp_path):
        fx = FxService(cache_path=None)  # 无缓存，网络可能失败 → 兜底
        v = fx.convert(1234, "GBP")
        assert v > 10000  # 兜底表 1GBP=9.11 → ~11241

    def test_cny_passthrough(self):
        fx = FxService()
        assert fx.convert(4380, "CNY") == 4380


class TestSkyscannerConcurrency:
    @pytest.mark.asyncio
    async def test_fetch_many_parallel_with_failure_isolation(self, monkeypatch):
        """§48: 并发中单 query 失败不影响其它；限流生效。"""
        adapter = SkyscannerAdapter(config=SkyscannerConfig(request_delay_sec=0))
        calls = []

        def fake_fetch(q):
            calls.append(q.origin)
            if q.origin == "FAIL":
                from universal_agent.adapters.skyscanner import SourceUnavailable
                raise SourceUnavailable("boom")
            return [RawListing.model_validate({
                "listing_id": f"l-{q.origin}", "source": "skyscanner",
                "marketplace_id": "skyscanner", "task_id": "t1",
                "origin_airport": q.origin, "dest_airport": "ZQN",
                "depart_date": q.depart_date, "return_date": q.return_date,
                "nights": 7, "price_cny": 5000.0,
                "outbound": {"segments": [], "total_min": 600, "stops": 0},
                "inbound": {"segments": [], "total_min": 480, "stops": 0},
            })]

        adapter.fetch = fake_fetch  # type: ignore[method-assign]
        queries = [
            FlightQuery(origin="PVG", destination="ZQN", depart_date="2026-08-31",
                        return_date="2026-09-07", nights=7),
            FlightQuery(origin="FAIL", destination="ZQN", depart_date="2026-08-31",
                        return_date="2026-09-07", nights=7),
            FlightQuery(origin="HGH", destination="ZQN", depart_date="2026-08-31",
                        return_date="2026-09-07", nights=7),
        ]
        out = await adapter.fetch_many(queries, max_concurrency=2)
        assert len(out) == 2  # FAIL 被隔离，2 条成功
        assert {l.origin_airport for l in out} == {"PVG", "HGH"}


class TestOfficialRegistry:
    def test_noop_source_returns_none(self):
        reg = OfficialSourceRegistry()
        reg.register("airline-x", NoOpOfficialVerifier())
        listing = RawListing.model_validate({
            "listing_id": "l1", "source": "skyscanner", "marketplace_id": "skyscanner",
            "task_id": "t1", "origin_airport": "PVG", "dest_airport": "ZQN",
            "depart_date": "2026-08-31", "return_date": "2026-09-07", "nights": 7,
            "price_cny": 5000.0,
            "outbound": {"segments": [], "total_min": 600, "stops": 0},
            "inbound": {"segments": [], "total_min": 480, "stops": 0},
        })
        assert reg.verify(listing) is None  # 骨架：无真实源时不伪造结果

    def test_stub_official_verify_tier3(self):
        reg = OfficialSourceRegistry()
        reg.register("airline-nz", StubOfficialVerifier(price=4900.0))
        listing = RawListing.model_validate({
            "listing_id": "l1", "source": "skyscanner", "marketplace_id": "skyscanner",
            "task_id": "t1", "origin_airport": "PVG", "dest_airport": "ZQN",
            "depart_date": "2026-08-31", "return_date": "2026-09-07", "nights": 7,
            "price_cny": 5000.0,
            "outbound": {"segments": [], "total_min": 600, "stops": 0},
            "inbound": {"segments": [], "total_min": 480, "stops": 0},
        })
        result = reg.verify(listing, available=["airline-nz"])
        assert result is not None
        assert result.verified_by == "deterministic_T3"
        assert result.passed is True

    def test_failing_source_degrades(self):
        class Boom:
            def verify(self, listing):
                raise RuntimeError("airline down")

        reg = OfficialSourceRegistry()
        reg.register("airline-x", Boom())
        listing = RawListing.model_validate({
            "listing_id": "l1", "source": "s", "marketplace_id": "s", "task_id": "t1",
            "origin_airport": "PVG", "dest_airport": "ZQN",
            "depart_date": "2026-08-31", "return_date": "2026-09-07", "nights": 7,
            "price_cny": 5000.0,
            "outbound": {"segments": [], "total_min": 600, "stops": 0},
            "inbound": {"segments": [], "total_min": 480, "stops": 0},
        })
        assert reg.verify(listing) is None
        assert reg.health()["airline-x"] == "DEGRADED"
