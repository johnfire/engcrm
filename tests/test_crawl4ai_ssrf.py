"""The headless-browser fetcher must apply the same public-address rule as the plain fetchers."""
from unittest.mock import AsyncMock, patch

import pytest

from gcrm.research.dossier import Crawl4AIFetcher


@pytest.fixture
def fetcher():
    instance = Crawl4AIFetcher()
    instance._ready = True  # as if crawl4ai were installed
    return instance


@pytest.mark.parametrize("url", ["http://169.254.169.254/latest/meta-data/", "http://127.0.0.1:8085/",
                                 "http://100.64.0.1/", "file:///etc/passwd", "http://localhost/admin"])
def test_a_non_public_url_is_never_handed_to_the_browser(fetcher, url):
    with patch.object(Crawl4AIFetcher, "_async_fetch", new=AsyncMock()) as browser, \
         patch("gcrm.research.dossier._cache_get", return_value=None):
        assert fetcher.fetch_page(url) is None
    browser.assert_not_called()


def test_a_non_public_landing_page_ends_the_domain_crawl(fetcher):
    with patch.object(Crawl4AIFetcher, "_async_fetch", new=AsyncMock()) as browser, \
         patch("gcrm.research.dossier._cache_get", return_value=None):
        assert fetcher.fetch_domain_pages("example.test", "http://127.0.0.1/") == []
    browser.assert_not_called()
