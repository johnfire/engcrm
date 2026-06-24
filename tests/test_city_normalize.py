"""City normalization via Nominatim (OSM). httpx is mocked — no network."""
from unittest.mock import patch, MagicMock

from gcrm.tools.search import normalize_city


def _mock_response(rows):
    resp = MagicMock()
    resp.json.return_value = rows
    resp.raise_for_status.return_value = None
    return resp


class TestNormalizeCity:
    def test_expands_variant_and_ranks(self):
        rows = [
            {"name": "Landsberg am Lech", "addresstype": "town",
             "address": {"town": "Landsberg am Lech", "state": "Bayern"}},
            {"name": "Landsberg", "addresstype": "town",
             "address": {"town": "Landsberg", "state": "Sachsen-Anhalt"}},
        ]
        with patch("gcrm.tools.search.httpx.get", return_value=_mock_response(rows)):
            out = normalize_city("Landsberg")
        assert [c["name"] for c in out] == ["Landsberg am Lech", "Landsberg"]
        assert out[0]["state"] == "Bayern"

    def test_filters_non_place_results(self):
        rows = [
            {"name": "Landsberger Allee", "addresstype": "road",
             "address": {"road": "Landsberger Allee"}},
            {"name": "München", "addresstype": "city",
             "address": {"city": "München", "state": "Bayern"}},
        ]
        with patch("gcrm.tools.search.httpx.get", return_value=_mock_response(rows)):
            out = normalize_city("x")
        assert [c["name"] for c in out] == ["München"]  # the road is dropped

    def test_typo_returns_empty(self):
        with patch("gcrm.tools.search.httpx.get", return_value=_mock_response([])):
            assert normalize_city("Münhen") == []

    def test_network_error_returns_empty(self):
        with patch("gcrm.tools.search.httpx.get", side_effect=RuntimeError("boom")):
            assert normalize_city("Augsburg") == []

    def test_blank_makes_no_request(self):
        with patch("gcrm.tools.search.httpx.get") as get:
            assert normalize_city("  ") == []
        get.assert_not_called()
