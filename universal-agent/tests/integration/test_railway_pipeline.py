"""Railway 全流程测试（P23）— 评分/协调器/机会/通知 + 12306 真实数据。"""
from __future__ import annotations

from pathlib import Path

import pytest

from universal_agent.core.contracts import RawRailway, TaskSpec, TaskType
from universal_agent.events import InProcessEventBus
from universal_agent.registry import MarketplaceManifest, SkillRegistry

BASE = Path(__file__).resolve().parent.parent.parent


def _raw(train_no="G7357", depart="08:00", arrive="09:36", seat="二等座",
         avail="06", duration="01:36") -> RawRailway:
    return RawRailway(
        railway_id=f"railway_12306:0:{train_no}:{seat}", source="railway_12306",
        marketplace_id="railway_12306", task_id="t1", train_no=train_no,
        origin_city="上海", dest_city="杭州东", depart_date="2026-08-20",
        depart_time=depart, arrive_time=arrive, seat_class=seat,
        price_cny=0.0, extra={"available": avail, "duration": duration})


class TestRailwayScoring:
    def test_available_beats_soldout(self):
        from universal_agent.domains.railway.scoring import score_railway
        avail = score_railway(_raw(avail="06"))["total"]
        soldout = score_railway(_raw(avail="0"))["total"]
        assert avail > soldout, "有票必须高于售罄"

    def test_morning_beats_late(self):
        from universal_agent.domains.railway.scoring import score_railway
        morning = score_railway(_raw(depart="07:00"))["schedule"]
        late = score_railway(_raw(depart="23:00"))["schedule"]
        assert morning > late

    def test_unknown_availability_neutral(self):
        from universal_agent.domains.railway.scoring import score_railway
        s = score_railway(_raw(avail=""))["available"]
        assert s == 0, "未知余票不得脑补（fail-closed）"


class TestRailwayCoordinator:
    def _coordinator(self, fetcher, notifier=None):
        reg = SkillRegistry()
        reg.register_marketplace(MarketplaceManifest(
            id="railway_12306", domains=["railway"], health="HEALTHY",
            capabilities={"search": True}, trust={"default_score": 0.85}))
        from universal_agent.coordinator.scanner import RailwayScanCoordinator
        return RailwayScanCoordinator(bus=InProcessEventBus(), registry=reg,
                                      fetchers={"railway_12306": fetcher},
                                      notifier=notifier, top_n=3)

    def test_full_pipeline_produces_opportunity_and_notification(self):
        import asyncio
        from universal_agent.coordinator.scanner import RailwayScanCoordinator

        def fetcher(q):
            return [_raw(train_no="G7357", avail="06"),
                    _raw(train_no="G7357", seat="一等座", avail="01"),
                    _raw(train_no="G7319", depart="09:35", arrive="11:00",
                         avail="04")]

        delivered: list = []
        coord = self._coordinator(fetcher, notifier=delivered.append)
        task = TaskSpec(id="rw", type=TaskType.WATCH, domain="railway",
                        search_space={"origin": ["上海"], "destination": ["杭州东"],
                                      "departure": {"start": "2026-08-20"}})
        out = asyncio.run(coord.scan(task))
        assert len(out.raw_railways) == 3
        assert len(out.candidates) == 2, "G7357/G7319 两个候选（座别为 offer）"
        assert len(out.ranked) == 3
        assert out.top and out.top[0].train_no == "G7357"
        assert out.opportunity is not None
        assert out.opportunity["train_no"] == "G7357"
        assert out.notified is True
        assert len(delivered) == 1, "机会通知必须投递"
        assert delivered[0]["event_type"] == "OPPORTUNITY_DETECTED"

    def test_soldout_no_opportunity_no_notification(self):
        import asyncio
        from universal_agent.coordinator.scanner import RailwayScanCoordinator

        def fetcher(q):
            return [_raw(avail="0"), _raw(avail="无")]

        delivered: list = []
        coord = self._coordinator(fetcher, notifier=delivered.append)
        task = TaskSpec(id="rw2", type=TaskType.WATCH, domain="railway",
                        search_space={"origin": ["上海"], "destination": ["杭州东"]})
        out = asyncio.run(coord.scan(task))
        assert out.opportunity is None
        assert out.notified is False
        assert delivered == [], "售罄不得通知"

    def test_source_failure_isolation(self):
        import asyncio
        from universal_agent.coordinator.scanner import RailwayScanCoordinator

        def bad_fetcher(q):
            raise RuntimeError("12306 down")

        delivered: list = []
        coord = self._coordinator(bad_fetcher, notifier=delivered.append)
        task = TaskSpec(id="rw3", type=TaskType.WATCH, domain="railway",
                        search_space={"origin": ["上海"], "destination": ["杭州东"]})
        out = asyncio.run(coord.scan(task))
        assert out.raw_railways == []
        assert out.opportunity is None
        assert out.notified is False, "源失败不得假通知（fail-closed）"


class TestRailwayLive:
    """12306 真实数据全流程（best-effort；限流时跳过并如实标注）。"""

    def test_live_full_pipeline_shanghai_hangzhou(self):
        import asyncio
        from universal_agent.adapters.railway import Railway12306Skill
        from universal_agent.coordinator.scanner import RailwayScanCoordinator

        skill = Railway12306Skill()
        if skill.health_check()["status"] != "HEALTHY":
            pytest.skip("12306 不可达/限流")
        reg = SkillRegistry()
        reg.register_marketplace(MarketplaceManifest(
            id="railway_12306", domains=["railway"], health="HEALTHY",
            capabilities={"search": True}, trust={"default_score": 0.85}))
        delivered: list = []
        coord = RailwayScanCoordinator(
            bus=InProcessEventBus(), registry=reg,
            fetchers={"railway_12306": skill.fetch}, notifier=delivered.append)
        task = TaskSpec(id="rw-live", type=TaskType.WATCH, domain="railway",
                        search_space={"origin": ["上海"], "destination": ["杭州东"],
                                      "departure": {"start": "2026-08-20"}})
        out = asyncio.run(coord.scan(task))
        if not out.raw_railways:
            pytest.skip("12306 限流返回空（可达性已在 health 验证）")
        assert out.raw_railways
        assert out.candidates
        assert out.ranked
        assert out.top, "必须有排名结果"
        # 有机会必须投递通知；无机会（售罄）也必须是合法结果
        assert out.notified == (out.opportunity is not None)
        assert len(delivered) == (1 if out.opportunity else 0)
