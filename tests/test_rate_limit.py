"""Tests for the auth rate limiter (logic + endpoint enforcement)."""
from unittest.mock import patch

from fastapi import Request
from fastapi.testclient import TestClient

import gcrm.api.main as main
from gcrm.api.rate_limit import FixedWindowRateLimiter, client_key

client = TestClient(main.app)


def test_allows_up_to_limit_then_blocks():
    limiter = FixedWindowRateLimiter(max_attempts=3, window_seconds=60)
    assert [limiter.allow("ip") for _ in range(3)] == [True, True, True]
    assert limiter.allow("ip") is False


def test_separate_keys_have_independent_budgets():
    limiter = FixedWindowRateLimiter(max_attempts=1, window_seconds=60)
    assert limiter.allow("client-a") is True
    assert limiter.allow("client-b") is True
    assert limiter.allow("client-a") is False


def test_reset_clears_counts():
    limiter = FixedWindowRateLimiter(max_attempts=1, window_seconds=60)
    assert limiter.allow("ip") is True
    assert limiter.allow("ip") is False
    limiter.reset()
    assert limiter.allow("ip") is True


def _request_with_peer(peer: str, headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    return Request({
        "type": "http",
        "method": "POST",
        "path": "/login",
        "headers": headers or [],
        "client": (peer, 12345),
    })


def test_untrusted_peer_cannot_supply_client_ip(monkeypatch):
    monkeypatch.setattr("gcrm.config.TRUSTED_PROXY_IPS", frozenset({"127.0.0.1"}))
    request = _request_with_peer("198.51.100.2", [(b"x-forwarded-for", b"203.0.113.9")])
    assert client_key(request) == "198.51.100.2"


def test_trusted_proxy_can_supply_client_ip(monkeypatch):
    monkeypatch.setattr("gcrm.config.TRUSTED_PROXY_IPS", frozenset({"127.0.0.1"}))
    request = _request_with_peer("127.0.0.1", [(b"x-forwarded-for", b"203.0.113.9, 127.0.0.1")])
    assert client_key(request) == "203.0.113.9"


def test_socket_peer_is_used_without_forwarding_header():
    assert client_key(_request_with_peer("198.51.100.2")) == "198.51.100.2"


def test_token_endpoint_throttles_after_limit():
    # Patch out auth so the first attempts return 401 (no DB), then the limiter
    # kicks in with 429. The conftest fixture resets the limiter before this test.
    with patch("gcrm.api.routers.api_auth.get_user_by_email", return_value=None), \
         patch("gcrm.api.routers.api_auth.authenticate", return_value=None):
        codes = [
            client.post("/api/auth/token", json={"email": "a@b.com", "password": "x"}).status_code
            for _ in range(12)
        ]
    assert codes[:10] == [401] * 10
    assert codes[10] == 429 and codes[11] == 429
