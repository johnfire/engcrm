"""SSRF guard for fetch_page: only public http(s) URLs are allowed."""
from unittest.mock import patch

import httpx

from gcrm.tools.search import fetch_page, is_public_http_url


def test_blocks_loopback_private_and_metadata():
    blocked = [
        "http://127.0.0.1/",
        "http://localhost/admin",
        "http://[::1]/",
        "http://169.254.169.254/latest/meta-data/",  # cloud metadata
        "http://10.0.0.5/",
        "http://192.168.1.1/",
        "http://172.16.0.1/",
        "file:///etc/passwd",
        "ftp://example.com/",
        "gopher://example.com/",
        "not-a-url",
    ]
    for url in blocked:
        assert is_public_http_url(url) is False, url


def test_allows_public_ip_literals():
    # IP literals need no DNS, so this stays offline.
    assert is_public_http_url("http://8.8.8.8/") is True
    assert is_public_http_url("https://93.184.216.34/path") is True


def test_refuses_redirect_to_private_address():
    redirect = httpx.Response(
        302,
        headers={"location": "http://127.0.0.1/admin"},
        request=httpx.Request("GET", "https://public.example/"),
    )
    with patch("gcrm.config.BRIGHTDATA_API_TOKEN", ""), patch(
        "gcrm.tools.search.is_public_http_url", side_effect=[True, False]
    ), patch(
        "gcrm.tools.search.httpx.get", return_value=redirect
    ) as get:
        assert fetch_page("https://public.example/") == ""
    assert get.call_count == 1


def test_follows_public_redirect_after_revalidation():
    redirect = httpx.Response(
        302,
        headers={"location": "https://other.example/about"},
        request=httpx.Request("GET", "https://public.example/"),
    )
    page = httpx.Response(
        200,
        text="<h1>Public page</h1>",
        request=httpx.Request("GET", "https://other.example/about"),
    )
    with patch("gcrm.config.BRIGHTDATA_API_TOKEN", ""), patch(
        "gcrm.tools.search.is_public_http_url", side_effect=[True, True]
    ), patch(
        "gcrm.tools.search.httpx.get", side_effect=[redirect, page]
    ):
        assert fetch_page("https://public.example/") == "Public page"
