"""Hotel domain tests (§63): entity key / room normalization / scoring."""
from __future__ import annotations

from universal_agent.core.contracts import RawHotel
from universal_agent.domains.hotel import (
    entity_key,
    normalize_hotel,
    normalize_room,
    score_hotel,
)


def _hotel(**over) -> RawHotel:
    base = dict(
        hotel_id="h1", source="booking", marketplace_id="booking", task_id="t1",
        name="Lakeview Queenstown Hotel", city="Queenstown",
        address="10 Lake Esplanade, Queenstown", brand="Lakeview",
        lat=-45.031, lng=168.662,
        check_in="2026-08-31", check_out="2026-09-07", nights=7,
        room_name="Deluxe King Room with Breakfast",
        price_per_night_cny=1100.0, currency="CNY", rating=4.6,
    )
    base.update(over)
    return RawHotel.model_validate(base)


class TestHotelEntityKey:
    def test_same_hotel_same_key(self):
        a = _hotel()
        b = _hotel(hotel_id="h1b", source="agoda", marketplace_id="agoda")
        assert entity_key(a) == entity_key(b)

    def test_different_hotel_different_key(self):
        a = _hotel()
        b = _hotel(name="Heritage Queenstown")
        assert entity_key(a) != entity_key(b)


class TestRoomNormalization:
    def test_deluxe_king_breakfast(self):
        n = normalize_room("Deluxe King Room with Breakfast")
        assert n.room_grade == "deluxe"
        assert n.bed_type == "king"
        assert n.board == "breakfast"

    def test_suite(self):
        assert normalize_room("Suite with Lake View").room_grade == "suite"

    def test_standard_twin_no_board(self):
        n = normalize_room("Superior Twin Room")
        assert n.room_grade == "superior"
        assert n.bed_type == "twin"
        assert n.board == "none"


class TestHotelNormalize:
    def test_produces_candidate_offer_quote(self):
        cand, offer, quote, evidence = normalize_hotel(_hotel(), "t1")
        assert cand.domain == "hotel"
        assert cand.attributes["room_grade"] == "deluxe"
        assert offer.terms["nights"] == 7
        assert quote.price.amount == 1100.0
        assert evidence.field == "price_per_night"
        assert evidence.source == "booking"


class TestHotelScoring:
    def test_cheapest_scores_higher_on_price(self):
        a = _hotel(hotel_id="a", name="A", price_per_night_cny=800)
        b = _hotel(hotel_id="b", name="B", price_per_night_cny=1200)
        sa = score_hotel(a, market_min=800)
        sb = score_hotel(b, market_min=800)
        assert sa["components"]["price"] > sb["components"]["price"]

    def test_higher_rating_scores_higher(self):
        a = _hotel(hotel_id="a", name="A", rating=4.8)
        b = _hotel(hotel_id="b", name="B", rating=3.5)
        sa = score_hotel(a, market_min=800)
        sb = score_hotel(b, market_min=800)
        assert sa["components"]["rating"] > sb["components"]["rating"]

    def test_total_bounded(self):
        s = score_hotel(_hotel(), market_min=800)
        assert 0 <= s["total"] <= 100
