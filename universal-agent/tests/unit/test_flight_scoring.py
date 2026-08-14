"""Flight scoring + Top5 ranking tests (§32, §61)."""
from __future__ import annotations

from universal_agent.core.contracts import RawListing
from universal_agent.core.ranking import rank_top_n
from universal_agent.domains.flight.scoring import score_listing


def _listing(lid, origin, price, stops, total_min, dep_time="08:00") -> RawListing:
    segs = [
        {"airline": "NZ", "flight_no": f"NZ{lid}", "dep_airport": origin,
         "arr_airport": "ZQN", "dep_time": dep_time, "arr_time": "21:00",
         "dep_date": "2026-08-31", "arr_date": "2026-08-31", "duration_min": 600},
    ]
    if stops > 0:
        segs.insert(0, {"airline": "MU", "flight_no": f"MU{lid}", "dep_airport": origin,
                        "arr_airport": "AKL", "dep_time": dep_time, "arr_time": "12:00",
                        "dep_date": "2026-08-31", "arr_date": "2026-08-31", "duration_min": 300})
    return RawListing.model_validate({
        "listing_id": lid, "source": "ctrip", "marketplace_id": "ctrip", "task_id": "t1",
        "origin_airport": origin, "dest_airport": "ZQN",
        "depart_date": "2026-08-31", "return_date": "2026-09-07", "nights": 7,
        "price_cny": price,
        "outbound": {"segments": segs, "total_min": total_min, "stops": stops,
                     "layovers": [120] if stops else [], "layover_airports": ["AKL"] if stops else [],
                     "overnight_layover": False, "airport_change": False, "self_transfer": False},
        "inbound": {"segments": [{"airline": "NZ", "flight_no": f"NZR{lid}", "dep_airport": "ZQN",
                                  "arr_airport": origin, "dep_time": "10:00", "arr_time": "18:00",
                                  "dep_date": "2026-09-07", "arr_date": "2026-09-07", "duration_min": 480}],
                    "total_min": 480, "stops": 0, "layovers": [],
                    "layover_airports": [], "overnight_layover": False,
                    "airport_change": False, "self_transfer": False},
        "luggage": {"checked": "2件23kg"},
    })


class TestScoring:
    def test_lowest_price_scores_highest_on_price(self):
        a = _listing("a", "PVG", 4000, 0, 600)
        b = _listing("b", "PVG", 5000, 0, 600)
        sa = score_listing(a, market_min=4000)
        sb = score_listing(b, market_min=4000)
        assert sa["components"]["price"] > sb["components"]["price"]

    def test_direct_beats_stops(self):
        a = _listing("a", "PVG", 5000, 0, 600)
        b = _listing("b", "PVG", 4800, 1, 900)
        sa = score_listing(a, market_min=4800)
        sb = score_listing(b, market_min=4800)
        assert sa["components"]["stops"] == 100.0
        assert sb["components"]["stops"] == 60.0

    def test_total_bounded_0_100(self):
        s = score_listing(_listing("a", "PVG", 4000, 0, 600), market_min=4000)
        assert 0 <= s["total"] <= 100


class TestRanker:
    def test_top1_is_best_score(self):
        listings = [
            _listing("a", "PVG", 4000, 0, 600),
            _listing("b", "PVG", 5000, 1, 900),
            _listing("c", "HGH", 4500, 0, 700),
        ]
        prices = [l.price_cny for l in listings]
        mm = min(prices)
        scored = {l.listing_id: score_listing(l, mm) for l in listings}
        top = rank_top_n(listings, scored, top_n=5)
        assert len(top) >= 1
        assert top[0].price_cny == 4000  # cheapest + direct → best

    def test_top5_diversity_per_origin(self):
        listings = [
            _listing("a", "PVG", 4000, 0, 600),
            _listing("b", "HGH", 4500, 0, 700),
            _listing("c", "SHA", 4700, 0, 750),
            _listing("d", "PVG", 4100, 1, 800),
            _listing("e", "PVG", 4900, 1, 850),
            _listing("f", "HGH", 5200, 1, 900),
        ]
        mm = min(l.price_cny for l in listings)
        scored = {l.listing_id: score_listing(l, mm) for l in listings}
        top = rank_top_n(listings, scored, top_n=5)
        assert len(top) == 5
        origins = {t.origin_airport for t in top}
        assert origins == {"PVG", "HGH", "SHA"}  # all three origins represented

    def test_empty_returns_empty(self):
        assert rank_top_n([], {}, top_n=5) == []
