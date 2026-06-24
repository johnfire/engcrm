"""SSRF guard for fetch_page: only public http(s) URLs are allowed."""
from gcrm.tools.search import _is_public_http_url


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
        assert _is_public_http_url(url) is False, url


def test_allows_public_ip_literals():
    # IP literals need no DNS, so this stays offline.
    assert _is_public_http_url("http://8.8.8.8/") is True
    assert _is_public_http_url("https://93.184.216.34/path") is True
