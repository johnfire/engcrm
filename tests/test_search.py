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


@pytest.mark.network
def test_live_search_returns_results():
    """A real query against the live backend — the check the offline tests cannot make.

    Uses a long-lived institutional site so it is not flaky on content churn.
    """
    results = search.web_search("Fraunhofer IIS Erlangen", max_results=5)
    assert results, "web_search returned nothing — the search backend is broken again"
    assert any(r["url"].startswith("http") for r in results)
