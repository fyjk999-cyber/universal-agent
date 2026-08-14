"""Replay tests (§47): fixtures → normalize/dedup/score/rank without network."""
from __future__ import annotations

from pathlib import Path

from universal_agent.adapters.replay import load_fixtures, make_fetcher
from universal_agent.core.contracts import RawListing
from universal_agent.domains.flight import entity_key

FIXTURES = Path(__file__).resolve().parent / "fixtures"


class TestReplayFixtures:
    def test_ctrip_fixtures_load(self):
        listings = load_fixtures(FIXTURES, "ctrip")
        assert len(listings) == 3
        assert all(isinstance(l, RawListing) for l in listings)

    def test_fliggy_fixtures_load(self):
        listings = load_fixtures(FIXTURES, "fliggy")
        assert len(listings) == 2

    def test_missing_source_returns_empty(self):
        assert load_fixtures(FIXTURES, "nonexistent") == []

    def test_fetcher_filters_by_origin_and_date(self):
        fetch = make_fetcher(FIXTURES, "ctrip", date_filter=True)
        from universal_agent.coordinator.query_planner import FlightQuery
        q = FlightQuery(origin="HGH", destination="ZQN",
                        depart_date="2026-08-31", return_date="2026-09-07", nights=7)
        got = fetch(q)
        assert got and all(l.depart_date == "2026-08-31" for l in got)
        assert all(l.origin_airport == "HGH" for l in got)
        # same date but different origin must NOT be returned
        q2 = FlightQuery(origin="PVG", destination="ZQN",
                         depart_date="2026-08-31", return_date="2026-09-07", nights=7)
        got2 = fetch(q2)
        assert all(l.origin_airport == "PVG" for l in got2)

    def test_cross_source_entity_resolution(self):
        """Same real itinerary from ctrip + fliggy → same entity_key (§21)."""
        ctrip = load_fixtures(FIXTURES, "ctrip")
        fliggy = load_fixtures(FIXTURES, "fliggy")
        mu779_ctrip = next(l for l in ctrip if l.depart_date == "2026-08-30")
        mu779_fliggy = next(l for l in fliggy if l.depart_date == "2026-08-30")
        assert mu779_ctrip.price_cny != mu779_fliggy.price_cny  # different offers
        assert entity_key(mu779_ctrip) == entity_key(mu779_fliggy)  # same candidate
