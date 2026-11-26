"""Oversized request bodies are refused before any handler or the CSRF check reads them."""
import json

import pytest
from fastapi.testclient import TestClient

import gcrm.api.main as main
from gcrm import config
from gcrm.api import body_limit
from gcrm.api.body_limit import BodyLimitMiddleware


async def read_everything_app(scope, receive, send):
    """A bare ASGI app: reads the whole body and answers with its length."""
    size = 0
    while True:
        message = await receive()
        size += len(message.get("body", b""))
        if not message.get("more_body", False):
            break
    body = json.dumps({"size": size}).encode()
    await send({"type": "http.response.start", "status": 200,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
    await send({"type": "http.response.body", "body": body})


@pytest.fixture
def small_limits(monkeypatch):
    monkeypatch.setattr(config, "MAX_BODY_BYTES", 1000)
    monkeypatch.setattr(config, "MAX_UPLOAD_BYTES", 5000)
    monkeypatch.setattr(body_limit, "MULTIPART_SLACK_BYTES", 0)


def isolated():
    return TestClient(BodyLimitMiddleware(read_everything_app))


def test_a_body_under_the_limit_passes_through(small_limits):
    response = isolated().post("/x", content=b"a" * 900)
    assert response.status_code == 200 and response.json() == {"size": 900}


def test_a_declared_length_over_the_limit_is_refused(small_limits):
    response = isolated().post("/x", content=b"a" * 1001)
    assert response.status_code == 413
    assert response.json() == {"detail": "Request too large"}


def test_a_streamed_body_with_no_length_is_cut_off_at_the_limit(small_limits):
    def chunks():
        for _ in range(20):
            yield b"a" * 100

    response = isolated().post("/x", content=chunks())
    assert response.status_code == 413


def test_a_garbage_content_length_is_refused(small_limits):
    response = isolated().post("/x", content=b"a", headers={"content-length": "lots"})
    assert response.status_code == 413


def test_multipart_gets_the_upload_limit_not_the_form_limit(small_limits):
    files = {"image": ("card.jpg", b"a" * 3000, "image/jpeg")}
    assert isolated().post("/x", files=files).status_code == 200
    files = {"image": ("card.jpg", b"a" * 6000, "image/jpeg")}
    assert isolated().post("/x", files=files).status_code == 413


def test_the_default_form_limit_fits_the_largest_legitimate_sync_push():
    """100 mutations (gcrm/sync/contracts.py) of four 20,000-character text fields
    (TEXT_LIMITS in api_record_edit.py) is about 8 MB of JSON."""
    worst_case = 100 * 4 * 20_000
    assert config.MAX_BODY_BYTES > worst_case


def test_the_default_multipart_limit_covers_the_upload_cap():
    assert body_limit.body_limit("multipart/form-data; boundary=x") > config.MAX_UPLOAD_BYTES


def test_the_real_app_refuses_an_oversized_login_before_the_route_runs(monkeypatch):
    monkeypatch.setattr(config, "MAX_BODY_BYTES", 1000)
    client = TestClient(main.app)
    response = client.post("/login", data={"email": "a@b.de", "password": "x" * 5000})
    assert response.status_code == 413
    assert response.headers["x-content-type-options"] == "nosniff"  # still carries the security headers


def test_the_real_app_still_serves_a_normal_login_attempt():
    client = TestClient(main.app)
    response = client.post("/login", data={"email": "nobody@example.test", "password": "wrong-password"})
    assert response.status_code == 401


def test_the_real_app_cuts_off_a_streamed_login_body_with_no_declared_length(monkeypatch):
    monkeypatch.setattr(config, "MAX_BODY_BYTES", 1000)
    client = TestClient(main.app)

    def chunks():
        for _ in range(50):
            yield b"password=" + b"x" * 100 + b"&"

    response = client.post("/login", content=chunks(),
                           headers={"content-type": "application/x-www-form-urlencoded"})
    assert response.status_code == 413
