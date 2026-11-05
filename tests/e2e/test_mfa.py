"""Two-factor authentication through real login routes and PostgreSQL."""
import re
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from gcrm.api.main import app
from gcrm.api.security import encrypt_totp_secret, hash_password
from gcrm.api.totp import _totp_code
from gcrm.config import ACCOUNT_ENCRYPTION_KEY
from gcrm.db.connection import db
from gcrm.tools.db_users import create_user

pytestmark = [pytest.mark.e2e, pytest.mark.security_boundary]
PASSWORD = "Fictional-two-factor-password"
EMAIL = "two-factor@example.test"
SECRET = "JBSWY3DPEHPK3PXP"


@pytest.fixture
def mfa_user(clean_database):
    user_id = create_user(EMAIL, hash_password(PASSWORD))
    with db() as connection:
        connection.cursor().execute(
            "UPDATE users SET mfa_enabled=TRUE,mfa_secret_encrypted=%s WHERE id=%s",
            (encrypt_totp_secret(SECRET, ACCOUNT_ENCRYPTION_KEY), user_id),
        )
    return user_id


def browser():
    client = TestClient(app, base_url="https://testserver", follow_redirects=False)
    page = client.get("/login")
    token = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
    client.headers.update({"Origin": "https://testserver", "X-CSRF-Token": token})
    return client


def post_login(client, code=""):
    return client.post("/login", data={"email": EMAIL, "password": PASSWORD, "mfa_code": code})


def refresh_csrf(client, path="/settings/two-factor"):
    page = client.get(path)
    token = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
    client.headers["X-CSRF-Token"] = token
    return page


def account_row(user_id):
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT * FROM users WHERE id=%s", (user_id,))
        return cursor.fetchone()


def enroll(client):
    response = client.post("/settings/two-factor/start", data={"current_password": PASSWORD})
    assert response.status_code == 200, response.text
    secret = re.search(r'<code>([A-Z2-7]{32})</code>', response.text).group(1)
    response = client.post("/settings/two-factor/enable", data={
        "current_password": PASSWORD, "mfa_code": _totp_code(secret, 1234560000),
    })
    assert response.status_code == 200, response.text
    codes = re.findall(r'<li><code>([a-f0-9]{32})</code>', response.text)
    assert len(codes) == 10
    assert response.headers["cache-control"] == "private, no-store"
    return secret, codes


@pytest.mark.parametrize("code", ["", "not-a-code"])
def test_web_password_alone_never_issues_a_session_for_mfa_account(mfa_user, code):
    client = browser()
    response = client.post("/login", data={"email": EMAIL, "password": PASSWORD, "mfa_code": code})
    assert response.status_code == 401
    assert client.get("/settings").status_code == 307


@pytest.mark.parametrize("code", ["", "not-a-code"])
def test_mobile_password_alone_never_issues_a_token_for_mfa_account(mfa_user, code):
    response = TestClient(app).post("/api/auth/token", json={
        "email": EMAIL, "password": PASSWORD, "mfa_code": code,
    })
    assert response.status_code == 401
    assert "token" not in response.json()


def test_valid_totp_logs_in_and_cannot_be_replayed_across_web_and_phone(mfa_user):
    with patch("gcrm.api.totp.time", SimpleNamespace(time=lambda: 1234560000)):
        code = _totp_code(SECRET, 1234560000)
        client = browser()
        assert post_login(client, code).status_code == 303
        assert client.get("/settings").status_code == 200
        replay = TestClient(app).post("/api/auth/token", json={
            "email": EMAIL, "password": PASSWORD, "mfa_code": code,
        })
        assert replay.status_code == 401
    with patch("gcrm.api.totp.time", SimpleNamespace(time=lambda: 1234560030)):
        response = TestClient(app).post("/api/auth/token", json={
            "email": EMAIL, "password": PASSWORD, "mfa_code": _totp_code(SECRET, 1234560030),
        })
        assert response.status_code == 200
        assert TestClient(app).get("/api/auth/me", headers={
            "Authorization": f"Bearer {response.json()['token']}",
        }).status_code == 200


def test_enrollment_recovery_and_disable_complete_flow(clean_database):
    user_id = create_user(EMAIL, hash_password(PASSWORD))
    token = TestClient(app).post("/api/auth/token", json={"email": EMAIL, "password": PASSWORD}).json()["token"]
    client = browser()
    assert post_login(client).status_code == 303
    refresh_csrf(client)
    with patch("gcrm.api.totp.time", SimpleNamespace(time=lambda: 1234560000)):
        secret, codes = enroll(client)
    account = account_row(user_id)
    assert account["mfa_enabled"] is True
    assert secret not in account["mfa_secret_encrypted"]
    assert not set(codes) & set(account["mfa_recovery_hashes"])
    assert account["mfa_pending_secret"] is None
    assert client.get("/settings").status_code == 307
    assert TestClient(app).get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    client = browser()
    assert post_login(client, codes[0]).status_code == 303
    refresh_csrf(client)
    assert client.post("/settings/two-factor/disable", data={
        "current_password": "wrong", "mfa_code": codes[1],
    }).status_code == 400
    assert account_row(user_id)["mfa_enabled"] is True
    response = client.post("/settings/two-factor/disable", data={
        "current_password": PASSWORD, "mfa_code": codes[1],
    })
    assert response.status_code == 200
    account = account_row(user_id)
    assert account["mfa_enabled"] is False
    assert account["mfa_recovery_hashes"] == []
    assert account["mfa_secret_encrypted"] is None
    assert client.get("/settings").status_code == 307
    client = browser()
    assert post_login(client).status_code == 303


def test_setup_requires_password_proof_code_and_unexpired_seed(clean_database):
    user_id = create_user(EMAIL, hash_password(PASSWORD))
    client = browser()
    assert post_login(client).status_code == 303
    refresh_csrf(client)
    assert client.post("/settings/two-factor/start", data={"current_password": "wrong"}).status_code == 400
    assert account_row(user_id)["mfa_pending_secret"] is None
    setup = client.post("/settings/two-factor/start", data={"current_password": PASSWORD})
    assert setup.status_code == 200
    secret = re.search(r'<code>([A-Z2-7]{32})</code>', setup.text).group(1)
    assert client.post("/settings/two-factor/enable", data={
        "current_password": PASSWORD, "mfa_code": "not-a-code",
    }).status_code == 400
    with db() as connection:
        connection.cursor().execute("UPDATE users SET mfa_pending_expires_at=NOW()-INTERVAL '1 second' WHERE id=%s", (user_id,))
    with patch("gcrm.api.totp.time", SimpleNamespace(time=lambda: 1234560000)):
        assert client.post("/settings/two-factor/enable", data={
            "current_password": PASSWORD, "mfa_code": _totp_code(secret, 1234560000),
        }).status_code == 400
    assert account_row(user_id)["mfa_enabled"] is False


def test_recovery_code_is_consumed_once_even_for_concurrent_logins(clean_database):
    from gcrm.tools.db_mfa import verify_login_factor

    user_id = create_user(EMAIL, hash_password(PASSWORD))
    client = browser()
    assert post_login(client).status_code == 303
    refresh_csrf(client)
    with patch("gcrm.api.totp.time", SimpleNamespace(time=lambda: 1234560000)):
        _, codes = enroll(client)
    with ThreadPoolExecutor(2) as executor:
        outcomes = list(executor.map(lambda _: verify_login_factor(user_id, codes[0], 1), range(2)))
    assert sorted(outcomes) == [False, True]
    assert len(account_row(user_id)["mfa_recovery_hashes"]) == 9
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT outcome FROM audit_log WHERE action='account.mfa_recovery_used'")
        assert [row["outcome"] for row in cursor.fetchall()] == ["success"]


def test_replacing_recovery_codes_revokes_old_codes_and_sessions(clean_database):
    user_id = create_user(EMAIL, hash_password(PASSWORD))
    client = browser()
    assert post_login(client).status_code == 303
    refresh_csrf(client)
    with patch("gcrm.api.totp.time", SimpleNamespace(time=lambda: 1234560000)):
        _, old_codes = enroll(client)
    client = browser()
    assert post_login(client, old_codes[0]).status_code == 303
    refresh_csrf(client)
    response = client.post("/settings/two-factor/recovery", data={
        "current_password": PASSWORD, "mfa_code": old_codes[1],
    })
    new_codes = re.findall(r'<li><code>([a-f0-9]{32})</code>', response.text)
    assert len(new_codes) == 10
    assert account_row(user_id)["token_version"] == 2
    assert client.get("/settings").status_code == 307
    client = browser()
    assert post_login(client, old_codes[2]).status_code == 401
    assert post_login(client, new_codes[0]).status_code == 303


def test_mfa_store_outage_refuses_both_login_routes(mfa_user):
    with patch("gcrm.api.auth.verify_login_factor", side_effect=RuntimeError("storage unavailable")):
        assert post_login(browser(), "123456").status_code == 503
        response = TestClient(app).post("/api/auth/token", json={
            "email": EMAIL, "password": PASSWORD, "mfa_code": "123456",
        })
        assert response.status_code == 503
        assert "token" not in response.json()


def test_factor_attempts_are_limited_per_account_and_stale_password_proof_fails(mfa_user):
    from gcrm.tools.db_mfa import verify_login_factor

    for _ in range(10):
        assert verify_login_factor(mfa_user, "wrong", 0) is False
    with patch("gcrm.api.totp.time", SimpleNamespace(time=lambda: 1234560000)):
        code = _totp_code(SECRET, 1234560000)
        assert verify_login_factor(mfa_user, code, 0) is False
        with db() as connection:
            connection.cursor().execute("UPDATE users SET mfa_blocked_until=NOW()-INTERVAL '1 second' WHERE id=%s", (mfa_user,))
        assert verify_login_factor(mfa_user, code, 99) is False
        assert verify_login_factor(mfa_user, code, 0) is True


def test_corrupted_seed_and_missing_factor_cannot_authenticate(mfa_user):
    with db() as connection:
        connection.cursor().execute("UPDATE users SET mfa_secret_encrypted='invalid-encrypted-seed' WHERE id=%s", (mfa_user,))
    assert post_login(browser(), "123456").status_code == 401


def test_password_reset_keeps_the_second_factor_required(mfa_user):
    from gcrm.api.auth import complete_password_reset
    from gcrm.tools.db_account_lifecycle import create_password_reset_token

    create_password_reset_token(mfa_user, "fictional-reset-token")
    assert complete_password_reset("fictional-reset-token", "New-two-factor-test-password")
    response = TestClient(app).post("/api/auth/token", json={
        "email": EMAIL, "password": "New-two-factor-test-password",
    })
    assert response.status_code == 401
    assert account_row(mfa_user)["mfa_enabled"] is True


def test_management_refuses_foreign_origin_and_unauthenticated_requests(clean_database):
    create_user(EMAIL, hash_password(PASSWORD))
    client = browser()
    assert client.get("/settings/two-factor").status_code == 307
    assert post_login(client).status_code == 303
    refresh_csrf(client)
    response = client.post("/settings/two-factor/start", data={"current_password": PASSWORD},
                           headers={"Origin": "https://sibling.testserver"})
    assert response.status_code == 403
