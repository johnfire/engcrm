"""web_search: result mapping, failure handling, and a live smoke test.

The predecessor package (`duckduckgo-search`) kept importing and kept returning
an empty list for every query instead of raising, so the research and enrichment
agents degraded to "the web has nothing" without a single error in the logs. The
offline tests below pin the contract; `test_live_search_returns_results` is the
one that actually notices that failure mode, so it is worth running whenever the
dependency moves.
"""
from unittest.mock import MagicMock, patch

import pytest

from gcrm.tools import search


def make_ddgs(rows):
    """DDGS is used as a context manager: `with DDGS() as ddgs: ddgs.text(...)`."""
    client = MagicMock()
    client.text.return_value = rows
    ddgs = MagicMock()
    ddgs.__enter__ = MagicMock(return_value=client)
    ddgs.__exit__ = MagicMock(return_value=False)
    return MagicMock(return_value=ddgs), client


class TestWebSearch:
    def test_maps_result_fields(self):
        rows = [{"title": "ZOLLHOF", "href": "https://zollhof.de/", "body": "Tech incubator"}]
        ddgs_cls, _ = make_ddgs(rows)
        with patch.object(search, "DDGS", ddgs_cls), patch("gcrm.tools.costs.record_search"):
            results = search.web_search("zollhof", max_results=3)
        assert results == [
            {"title": "ZOLLHOF", "url": "https://zollhof.de/", "snippet": "Tech incubator"}
        ]

    def test_passes_max_results_through(self):
        ddgs_cls, client = make_ddgs([])
        with patch.object(search, "DDGS", ddgs_cls), patch("gcrm.tools.costs.record_search"):
            search.web_search("anything", max_results=4)
        assert client.text.call_args.kwargs["max_results"] == 4

    def test_missing_keys_do_not_raise(self):
        ddgs_cls, _ = make_ddgs([{"href": "https://example.org"}])
        with patch.object(search, "DDGS", ddgs_cls), patch("gcrm.tools.costs.record_search"):
            results = search.web_search("partial")
        assert results == [{"title": "", "url": "https://example.org", "snippet": ""}]

    def test_backend_failure_returns_empty(self):
        ddgs_cls = MagicMock(side_effect=RuntimeError("backend down"))
        with patch.object(search, "DDGS", ddgs_cls), patch("gcrm.tools.costs.record_search"):
            assert search.web_search("boom") == []

    def test_backed_by_the_maintained_package(self):
        """`duckduckgo-search` was renamed to `ddgs`; the old one is a silent no-op."""
        assert search.DDGS.__module__.split(".")[0] == "ddgs"


class TestGoogleMapsSearch:
    """City scans text-search "{term} {city}" with no geo restriction; area/GPS
    scans drop the city from the query text and constrain geography with a
    locationRestriction circle instead — see docs/plans/2026-08-20-area-scanning-design.md."""

    def _mock_response(self, places):
        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json.return_value = {"places": places}
        return response

    def test_city_scan_has_city_in_query_and_no_location_restriction(self):
        response = self._mock_response([])
        with patch("gcrm.config.GOOGLE_MAPS_API_KEY", "test-key"), \
             patch("httpx.post", return_value=response) as post:
            search.google_maps_search("Handwerksbetrieb", "Augsburg", "DE")
        payload = post.call_args.kwargs["json"]
        assert payload["textQuery"] == "Handwerksbetrieb Augsburg"
        assert "locationRestriction" not in payload

    def test_area_scan_drops_city_from_query_and_adds_circle(self):
        response = self._mock_response([])
        with patch("gcrm.config.GOOGLE_MAPS_API_KEY", "test-key"), \
             patch("httpx.post", return_value=response) as post:
            search.google_maps_search(
                "Handwerksbetrieb", "Augsburg", "DE", lat=48.37, lon=10.90, radius_m=500,
            )
        payload = post.call_args.kwargs["json"]
        assert payload["textQuery"] == "Handwerksbetrieb"
        assert payload["locationRestriction"] == {
            "circle": {"center": {"latitude": 48.37, "longitude": 10.90}, "radius": 500}
        }

    def test_missing_api_key_returns_empty_without_a_request(self):
        with patch("gcrm.config.GOOGLE_MAPS_API_KEY", ""), patch("httpx.post") as post:
            results = search.google_maps_search("Handwerksbetrieb", "Augsburg")
        assert results == []
        post.assert_not_called()


class TestReverseGeocode:
    def test_resolves_city_from_address_components(self):
        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json.return_value = {
            "address": {"city": "Augsburg", "state": "Bavaria", "country_code": "de"}
        }
        with patch("httpx.get", return_value=response):
            result = search.reverse_geocode(48.37, 10.90)
        assert result == {"name": "Augsburg", "country": "DE", "state": "Bavaria"}

    def test_no_city_in_address_returns_none(self):
        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json.return_value = {"address": {"country_code": "de"}}
        with patch("httpx.get", return_value=response):
            assert search.reverse_geocode(0.0, 0.0) is None

    def test_request_failure_returns_none(self):
        with patch("httpx.get", side_effect=RuntimeError("timeout")):
            assert search.reverse_geocode(48.37, 10.90) is None


@pytest.mark.network
def test_live_search_returns_results():
    """A real query against the live backend — the check the offline tests cannot make.

    Uses a long-lived institutional site so it is not flaky on content churn.
    """
    results = search.web_search("Fraunhofer IIS Erlangen", max_results=5)
    assert results, "web_search returned nothing — the search backend is broken again"
    assert any(r["url"].startswith("http") for r in results)
