"""Password policy edges, uniform login timing, and request-id sanitising."""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import gcrm.api.auth as auth
import gcrm.api.main as main
from gcrm.api.auth import require_admin
from gcrm.api.security import password_problem

client = TestClient(main.app)

TWELVE = "abcdefghijkl"


@pytest.mark.parametrize("password,expected", [
    (TWELVE, None),
    (TWELVE[:-1], "short"),
    ("a" * 72, None),
    ("a" * 73, "long"),
    ("ü" * 36, None),        # 72 bytes
    ("ü" * 37, "long"),      # 74 bytes: bcrypt refuses more than 72 bytes
    ("ü" * 12, None),        # 12 characters
])
def test_password_problem_measures_characters_for_the_minimum_and_bytes_for_the_maximum(password, expected):
    assert password_problem(password) == expected


def test_a_too_long_reset_password_is_refused_without_using_up_the_reset_link():
    with patch("gcrm.api.auth.consume_password_reset_token") as consume:
        assert auth.complete_password_reset("token", "a" * 73) is False
    consume.assert_not_called()


def test_signup_refuses_a_too_long_password_before_consuming_the_invitation():
    with patch("gcrm.api.routers.account.accept_invitation") as accept:
        response = client.post("/signup", data={"email": "a@b.de", "password": "a" * 73,
                                                "invitation_token": "t"})
    assert response.status_code == 400
    accept.assert_not_called()


@pytest.mark.parametrize("known_user", [None, {"is_active": False, "password_hash": "x", "role": "admin",
                                               "id": 1, "email": "a@b.de"}])
def test_login_does_the_same_hashing_work_for_an_unknown_or_inactive_account(known_user):
    """An absent account must not answer faster than a present one, or the response time
    reveals which emails have accounts."""
    with patch("gcrm.api.auth.verify_password", return_value=False) as verify, \
         patch("gcrm.api.auth.ADMIN_PASSWORD", ""):
        assert auth.authenticate("a@b.de", "whatever-password", known_user) is None
    assert verify.call_count == 1


def test_a_real_account_is_still_checked_exactly_once():
    user = {"is_active": True, "password_hash": "hash", "role": "admin", "id": 1, "email": "a@b.de"}
    with patch("gcrm.api.auth.verify_password", return_value=True) as verify:
        assert auth.authenticate("a@b.de", "right-password!", user)["user_id"] == 1
    assert verify.call_count == 1


@pytest.fixture
def admin_session():
    main.app.dependency_overrides[require_admin] = lambda: "admin"
    yield
    main.app.dependency_overrides.pop(require_admin, None)


def test_an_admin_cannot_set_a_short_password_for_a_new_user(admin_session):
    with patch("gcrm.api.routers.users.get_user_by_email", return_value=None), \
         patch("gcrm.api.routers.users.create_user") as create:
        client.post("/users/add", data={"email": "a@b.de", "password": "short"}, follow_redirects=False)
    create.assert_not_called()


def test_an_admin_cannot_reset_to_a_short_or_too_long_password(admin_session):
    with patch("gcrm.api.routers.users.set_user_password") as set_password:
        client.post("/users/passwd", data={"email": "a@b.de", "password": "short"}, follow_redirects=False)
        client.post("/users/passwd", data={"email": "a@b.de", "password": "a" * 73}, follow_redirects=False)
    set_password.assert_not_called()


def test_the_flash_tells_the_admin_why(admin_session):
    with patch("gcrm.api.routers.users.get_user_by_email", return_value=None), \
         patch("gcrm.api.routers.users.create_user"), patch("gcrm.api.routers.users.list_users", return_value=[]):
        client.post("/users/add", data={"email": "a@b.de", "password": "short"}, follow_redirects=False)
        page = client.get("/users/")
    assert "at least 12 characters" in page.text


def test_a_sensible_request_id_is_echoed_back():
    response = client.get("/login", headers={"X-Request-ID": "req-123_ok.1"})
    assert response.headers["x-request-id"] == "req-123_ok.1"


@pytest.mark.parametrize("hostile", ["a" * 500, "has space", "semi;colon", "quote\"here", "<script>"])
def test_a_hostile_or_oversized_request_id_is_replaced(hostile):
    response = client.get("/login", headers={"X-Request-ID": hostile})
    echoed = response.headers["x-request-id"]
    assert echoed != hostile and 1 <= len(echoed) <= 64
