"""12306 Railway 源测试 — 真实公开接口（无 key）+ 映射正确性。"""
from __future__ import annotations

from pathlib import Path

import pytest

from universal_agent.adapters.railway import (
    Railway12306Skill,
    railway12306_marketplace_manifest,
)

FIXTURE_DIR = Path(__file__).resolve().parent.parent.parent / "tests" / "replay" / "fixtures"

# 真实 12306 queryG 记录（2026-08-15 实测样本，脱敏仅保留结构）
SAMPLE_RECORD = (
    "n/hpP/Bm6CzkmwUAnKiCGYVLxje8vJVgZQL6hBmT|预订|0h0000Z1780I|Z175|VAB|HZH|"
    "IMH|HZH|04:08|05:50|01:42|Y|xW3NlcsSuTJXxRCRboyF7wvjes0dQv0QTK7flNYG1XEYkseWr3ZpM%2BdMc9w%3D|"
    "20260818|3|B4|26|29|1|0||||7|||1|||有|20|||||104030W0|1431|0|0||"
    "1002350020401045000730069500211002353001|0|||||1|0#0#0#0#z#0#43#z|||CHN,CHN|||"
    "N#N#|43010454101105330069531007753200745||202608061445|Y|"
)


class _FakeClient:
    """注入固定响应的 12306 客户端替身（离线单测）。"""

    def __init__(self, trains):
        self._trains = trains

    def query_trains(self, from_city, to_city, date, exact_match=True):
        return self._trains

    def stations(self):
        return {"上海": "SHH", "杭州东": "HGH", "北京": "BJP"}


class TestRailwayMapping:
    def test_health_and_manifest(self):
        skill = Railway12306Skill()
        assert skill.prepare_action("x", {})["allowed"] is False
        assert railway12306_marketplace_manifest().domains == ["railway"]

    def test_search_maps_seat_records(self):
        trains = [{
            "train_no": "0h0000G73570", "number": "G7357",
            "from_code": "SHH", "to_code": "HGH",
            "from_city": "上海", "to_city": "杭州东",
            "depart": "08:00", "arrive": "09:36", "duration": "01:36",
            "bookable": "Y", "date": "20260820",
            "seats": {"商务座": "H3", "一等座": "01", "二等座": "06",
                      "硬卧": "1", "软卧": "0", "硬座": "0", "无座": ""},
        }]
        skill = Railway12306Skill(client=_FakeClient(trains))
        items = skill.search({"from_city": "上海", "to_city": "杭州东",
                              "date": "2026-08-20"})
        assert len(items) == 6, "非空座别都产出记录（含 余票=0 售罄；仅 无座=空 跳过）"
        seats = {i["seat_class"] for i in items}
        assert {"商务座", "一等座", "二等座", "硬卧", "软卧", "硬座"} <= seats

    def test_fetch_returns_raw_railway(self):
        trains = [{
            "train_no": "0h0000G73570", "number": "G7357",
            "from_code": "SHH", "to_code": "HGH",
            "from_city": "上海", "to_city": "杭州东",
            "depart": "08:00", "arrive": "09:36", "duration": "01:36",
            "bookable": "Y", "date": "20260820",
            "seats": {"二等座": "06", "一等座": "01"},
        }]
        skill = Railway12306Skill(client=_FakeClient(trains))
        raws = skill.fetch(("上海", "杭州东", "2026-08-20"))
        assert len(raws) == 2
        r = raws[0]
        assert r.train_no == "G7357"
        assert r.origin_city == "上海" and r.dest_city == "杭州东"
        assert r.depart_date == "2026-08-20"
        assert r.depart_time == "08:00" and r.arrive_time == "09:36"
        assert r.seat_class == "一等座"  # SEAT_CLASSES 顺序输出（一等座在二等座前）
        assert r.marketplace_id == "railway_12306"


class TestRailwayLive:
    """真实 12306 公开接口（无 key，best-effort；限流时跳过并如实标注）。"""

    def test_live_query_shanghai_hangzhou(self):
        skill = Railway12306Skill()
        h = skill.health_check()
        if h["status"] != "HEALTHY":
            pytest.skip(f"12306 不可达/限流: {h}")
        items = skill.search({"from_city": "上海", "to_city": "杭州东",
                              "date": "2026-08-20"})
        if not items:
            pytest.skip("12306 限流返回空（接口本身可达性已在 health 验证）")
        assert len(items) >= 1
        assert all(i["origin_city"] == "上海" for i in items), "精确车站匹配必须成立"
        assert all(i["depart_date"] == "2026-08-20" for i in items)
