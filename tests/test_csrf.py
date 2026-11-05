"""Token rendering and validation are exercised without bypassing browser guards."""
import pytest
from starlette.requests import Request

from gcrm.api.csrf import accepts_browser_write, protect_html_forms

pytestmark = pytest.mark.security_boundary


def request_for(headers, body=b"", method="POST", path="/settings/language"):
    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}
    return Request({"type": "http", "method": method, "scheme": "https", "path": path,
                    "query_string": b"", "server": ("site.test", 443), "session": {"csrf_token": "session-bound-token"},
                    "headers": [(b"host", b"site.test"), *[(key.encode(), value.encode()) for key, value in headers.items()]]}, receive)


@pytest.mark.parametrize("headers", [
    {}, {"origin": "https://evil.test"}, {"origin": "null"},
    {"origin": "https://site.test", "x-csrf-token": "wrong"},
    {"origin": "https://site.test", "x-csrf-token": "session-bound-token", "sec-fetch-site": "cross-site"},
])
async def test_missing_or_hostile_browser_proof_is_refused(headers):
    assert not await accepts_browser_write(request_for(headers))


@pytest.mark.parametrize("proof", [{"origin": "https://site.test"}, {"referer": "https://site.test/settings"}])
async def test_token_requires_same_origin_or_same_origin_referer(proof):
    assert await accepts_browser_write(request_for({**proof, "x-csrf-token": "session-bound-token"}))


async def test_native_form_token_is_accepted_without_header():
    request = request_for({"origin": "https://site.test", "content-type": "application/x-www-form-urlencoded"},
                          body=b"csrf_token=session-bound-token&ui_language=de")
    assert await accepts_browser_write(request)
    assert b"ui_language=de" in await request.body()


async def test_https_origin_works_behind_a_loopback_http_proxy(monkeypatch):
    monkeypatch.setattr("gcrm.api.csrf.SESSION_COOKIE_SECURE", True)
    request = request_for({"origin": "https://site.test", "x-csrf-token": "session-bound-token"})
    request.scope["scheme"] = "http"
    assert await accepts_browser_write(request)


def test_only_mutating_forms_get_hidden_tokens_and_full_pages_load_the_script():
    html = '<head></head><form method="get"></form><form method="post"></form><form hx-put="/value"></form>'
    rendered = protect_html_forms(html, "proof")
    assert '<form method="get"></form>' in rendered
    assert rendered.count('name="csrf_token" value="proof"') == 2
    assert 'src="/static/csrf.js"' in rendered


@pytest.mark.parametrize("path", ["/api/account/language", "/mcp", "/mcp/"])
async def test_bearer_protocols_do_not_require_cookie_tokens(path):
    assert await accepts_browser_write(request_for({}, path=path))
