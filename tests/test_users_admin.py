"""Admin users page: routes call the right db helpers, guard unauth, and render.
DB helpers are mocked; require_admin is overridden for the authed cases."""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import gcrm.api.main as main
from gcrm.api.auth import require_admin

client = TestClient(main.app)


@pytest.fixture
def admin_session():
    main.app.dependency_overrides[require_admin] = lambda: "admin"
    yield
    main.app.dependency_overrides.pop(require_admin, None)


def test_unauthenticated_is_blocked():
    # No session → require_admin → require_login → 307 redirect to /login.
    r = client.get("/users/", follow_redirects=False)
    assert r.status_code in (303, 307, 401, 403)


def test_page_renders(admin_session):
    with patch("gcrm.api.routers.users.list_users", return_value=[]):
        r = client.get("/users/")
    assert r.status_code == 200
    assert "Add user" in r.text


def test_add_user_creates_and_redirects(admin_session):
    with patch("gcrm.api.routers.users.get_user_by_email", return_value=None), \
         patch("gcrm.api.routers.users.create_user", return_value=1) as mc:
        r = client.post(
            "/users/add",
            data={"email": "A@B.com", "name": "A", "role": "admin", "password": "secret123"},
            follow_redirects=False,
        )
    assert r.status_code == 303
    assert mc.call_args.args[0] == "a@b.com"          # email normalized to lowercase
    assert mc.call_args.kwargs["role"] == "admin"


def test_add_user_rejects_duplicate(admin_session):
    with patch("gcrm.api.routers.users.get_user_by_email", return_value={"id": 1}), \
         patch("gcrm.api.routers.users.create_user") as mc:
        r = client.post("/users/add", data={"email": "a@b.com", "password": "x"},
                        follow_redirects=False)
    assert r.status_code == 303
    assert not mc.called                               # duplicate → not created


def test_reset_password(admin_session):
    with patch("gcrm.api.routers.users.set_user_password", return_value=True) as ms:
        r = client.post("/users/passwd", data={"email": "a@b.com"}, follow_redirects=False)
    assert r.status_code == 303
    assert ms.called


def test_disable_user(admin_session):
    with patch("gcrm.api.routers.users.set_user_active", return_value=True) as ms:
        r = client.post("/users/active", data={"email": "a@b.com", "active": "0"},
                        follow_redirects=False)
    assert r.status_code == 303
    assert ms.call_args.args == ("a@b.com", False)


def test_enable_user(admin_session):
    with patch("gcrm.api.routers.users.set_user_active", return_value=True) as ms:
        r = client.post("/users/active", data={"email": "a@b.com", "active": "1"},
                        follow_redirects=False)
    assert r.status_code == 303
    assert ms.call_args.args == ("a@b.com", True)
