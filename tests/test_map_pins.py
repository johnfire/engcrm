"""Map pins: which organizations are on the user's Google Maps lists. The pure parts
(reading Google's place id out of a link, the list filter) are checked here; the
database behaviour is in tests/integration/test_map_pins_db.py."""
from gcrm.api.routers.organizations import _build_organization_filters
from gcrm.tools.map_pins import COLD_CALL_CANDIDATES, place_key_from_url

# A real place link as Maps shows it after saving: the place's id is the first !1s.
PLACE_URL = (
    "https://www.google.com/maps/place/ASP+Dichtstoffe+GmbH/@48.1649005,10.8148139,862m/data=!3m2!1e3"
    "!5s0x479c1f79703fb131:0xc09d8afb2ff268dc!4m14!1m7!3m6!1s0x479c1f7973ddb70b:0x3456fcf4696e45ec"
    "!2sASP+Dichtstoffe+GmbH!8m2!3d48.164897!4d10.8173888!16s%2Fg%2F1xpwhrx4"
)


class TestPlaceKey:
    def test_reads_the_places_own_id_not_the_search_id(self):
        assert place_key_from_url(PLACE_URL) == "0x479c1f7973ddb70b:0x3456fcf4696e45ec"

    def test_a_link_without_a_place_id_has_none(self):
        assert place_key_from_url("https://www.google.com/maps/@48.1,10.8,15z") is None
        assert place_key_from_url("") is None
        assert place_key_from_url(None) is None

    def test_the_default_list_is_the_cold_call_one(self):
        assert COLD_CALL_CANDIDATES == "Cold call candidates"


class TestOnMapFilter:
    def _where(self, on_map):
        return _build_organization_filters("", "", "", "", on_map=on_map)

    def test_on_map_asks_for_a_live_pin(self):
        where, params = self._where("1")
        assert "EXISTS (SELECT 1 FROM map_pins" in where and "removed_at IS NULL" in where
        assert "NOT EXISTS" not in where
        assert params == []

    def test_not_on_map_asks_for_none(self):
        where, _ = self._where("0")
        assert "NOT EXISTS (SELECT 1 FROM map_pins" in where

    def test_no_filter_by_default(self):
        where, _ = self._where("")
        assert "map_pins" not in where
