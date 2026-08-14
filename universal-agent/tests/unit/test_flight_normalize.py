"""Flight domain + normalizer tests (§20, §21)."""
from __future__ import annotations

from universal_agent.core.contracts import RawListing
from universal_agent.domains.flight import entity_key, normalize_listing
from universal_agent.domains.flight.knowledge import candidate_attributes


def _listing(**over) -> RawListing:
    base = dict(
        listing_id="l1", source="ctrip", marketplace_id="ctrip",
        task_id="t1", origin_airport="PVG", dest_airport="ZQN",
        depart_date="2026-08-30", return_date="2026-09-06", nights=7,
        price_cny=4260.0,
        outbound={
            "segments": [
                {"airline": "MU", "flight_no": "MU779", "dep_airport": "PVG",
                 "arr_airport": "AKL", "dep_time": "00:15", "arr_time": "17:30",
                 "dep_date": "2026-08-30", "arr_date": "2026-08-30", "duration_min": 645},
                {"airline": "NZ", "flight_no": "NZ621", "dep_airport": "AKL",
                 "arr_airport": "ZQN", "dep_time": "19:30", "arr_time": "21:15",
                 "dep_date": "2026-08-30", "arr_date": "2026-08-30", "duration_min": 105},
            ],
            "total_min": 810, "stops": 1, "layovers": [120],
            "layover_airports": ["AKL"], "overnight_layover": False,
            "airport_change": False, "self_transfer": False,
        },
        inbound={
            "segments": [
                {"airline": "NZ", "flight_no": "NZ622", "dep_airport": "ZQN",
                 "arr_airport": "AKL", "dep_time": "10:00", "arr_time": "11:45",
                 "dep_date": "2026-09-06", "arr_date": "2026-09-06", "duration_min": 105},
                {"airline": "MU", "flight_no": "MU780", "dep_airport": "AKL",
                 "arr_airport": "PVG", "dep_time": "21:00", "arr_time": "05:45",
                 "dep_date": "2026-09-06", "arr_date": "2026-09-07", "duration_min": 735},
            ],
            "total_min": 870, "stops": 1, "layovers": [555],
            "layover_airports": ["AKL"], "overnight_layover": False,
            "airport_change": False, "self_transfer": False,
        },
        luggage={"checked": "2件23kg"},
    )
    base.update(over)
    return RawListing.model_validate(base)


class TestEntityKey:
    def test_same_itinerary_same_key(self):
        a = _listing()
        b = _listing(listing_id="l2", source="fliggy", marketplace_id="fliggy")
        assert entity_key(a) == entity_key(b)

    def test_different_date_different_key(self):
        a = _listing()
        b = _listing(depart_date="2026-08-31", return_date="2026-09-07")
        assert entity_key(a) != entity_key(b)

    def test_key_contains_core_fields(self):
        key = entity_key(_listing())
        assert "2026-08-30" in key
        assert "MU779" in key
        assert "PVG" in key
        assert "ZQN" in key


class TestNormalize:
    def test_produces_candidate_offer_quote_evidence(self):
        listing = _listing()
        cand, offer, quote, evidence = normalize_listing(listing, "t1")
        assert cand.domain == "flight"
        assert cand.entity_key == entity_key(listing)
        assert offer.marketplace_id == "ctrip"
        assert quote.price.amount == 4260.0
        assert evidence.field == "price"
        assert evidence.source == "ctrip"
        assert evidence.confidence == 0.9

    def test_quote_is_currency_aware(self):
        cand, offer, quote, evidence = normalize_listing(_listing(currency="USD", price_cny=600.0), "t1")
        assert quote.price.currency == "USD"
        assert quote.confidence == 0.7

    def test_candidate_attributes(self):
        listing = _listing()
        attrs = candidate_attributes(listing)
        assert attrs["origin"] == "PVG"
        assert attrs["stops_total"] == 2
        assert attrs["total_duration_min"] == 1680
