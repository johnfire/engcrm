"""Response protections and script nonces through the public web interface."""
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gcrm.api.main import app


@pytest.mark.parametrize("path,status", [("/login", 200), ("/users/", 307),
                                        ("/api/auth/me", 401), ("/does-not-exist", 404)])
def test_headers_cover_success_redirect_auth_error_and_not_found(path, status):
    response = TestClient(app, base_url="https://testserver", follow_redirects=False).get(path)
    assert response.status_code == status
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert "microphone=(self)" in response.headers["permissions-policy"]
    assert response.headers["cache-control"] == "private, no-store"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert "includeSubDomains" not in response.headers["strict-transport-security"]


def test_https_transport_policy_is_not_sent_for_local_http_staging():
    response = TestClient(app, base_url="http://testserver").get("/login")
    assert "strict-transport-security" not in response.headers


def test_login_scripts_have_fresh_nonces_and_no_inline_script_permission():
    client = TestClient(app)
    first, second = client.get("/login"), client.get("/login")
    nonce = re.search(r"'nonce-([A-Za-z0-9_-]+)'", first.headers["content-security-policy"]).group(1)
    assert nonce not in second.headers["content-security-policy"]
    assert f'nonce="{nonce}"' in first.text
    assert "script-src-attr 'none'" in first.headers["content-security-policy"]
    assert "'unsafe-inline'" not in first.headers["content-security-policy"].split("script-src ", 1)[1].split(";", 1)[0]
    assert "https://unpkg.com" not in first.text


def test_htmx_partial_requests_can_use_the_page_nonce_but_not_header_injection():
    client = TestClient(app)
    nonce = "FictionalPageNonce1234567890"
    response = client.get("/login", headers={"HX-Request": "true", "X-CSP-Nonce": nonce})
    assert f"'nonce-{nonce}'" in response.headers["content-security-policy"]
    response = client.get("/login", headers={"HX-Request": "true", "X-CSP-Nonce": "injected'; script-src *"})
    assert "injected" not in response.headers["content-security-policy"]
    response = client.get("/login", headers={"X-CSP-Nonce": nonce})
    assert f"'nonce-{nonce}'" not in response.headers["content-security-policy"]


def test_templates_use_nonce_scripts_and_declarative_form_events():
    templates = list(Path("gcrm/ui/templates").rglob("*.html"))
    assert templates
    for template in templates:
        source = template.read_text()
        assert not re.search(r'<(?:script|style)\b(?![^>]*\bnonce=)', source), template
        assert not re.search(r'\bon(?:click|change|submit|input|load|error)\s*=', source), template


def test_public_https_proxy_configuration_adds_transport_policy(monkeypatch):
    monkeypatch.setattr("gcrm.api.browser_headers.SESSION_COOKIE_SECURE", True)
    response = TestClient(app, base_url="http://internal-proxy").get("/login")
    assert response.headers["strict-transport-security"] == "max-age=31536000"


def test_unhandled_errors_still_have_security_headers():
    async def fail(request):
        raise RuntimeError("Fictional header regression")

    from starlette.routing import Route

    route = Route("/_fictional-header-error", fail)
    app.router.routes.append(route)
    try:
        response = TestClient(app, raise_server_exceptions=False).get("/_fictional-header-error")
        assert response.status_code == 500
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["cache-control"] == "private, no-store"
        assert "Fictional" not in response.text
    finally:
        app.router.routes.remove(route)
