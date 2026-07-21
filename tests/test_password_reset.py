"""Password reset: token lifecycle (db_account_lifecycle), the shared
request/complete logic in gcrm.api.auth, and both the web (/forgot-password,
/reset-password) and mobile (/api/auth/reset-request) surfaces. DB, email
sending, and token generation are mocked — these run without Postgres or a
live Proton Bridge."""
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

import gcrm.api.main as main
from gcrm.api import auth

client = TestClient(main.app)


def make_mock_conn(rows=None):
    cur = MagicMock()
    cur.fetchone.return_value = rows[0] if rows else None
    cur.fetchall.return_value = rows or []
    conn = MagicMock()
    conn.cursor.return_value = cur
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    return conn, cur


def active_user(user_id=7, email="a@b.com"):
    return {"id": user_id, "email": email, "role": "admin", "is_active": True,
            "password_hash": "x", "token_version": 0, "workspace_id": 1}


class TestTokenLifecycle:
    def test_create_stores_hashed_token(self):
        conn, cur = make_mock_conn()
        with patch("gcrm.tools.db_account_lifecycle.db") as mock_db:
            mock_db.return_value.__enter__.return_value = conn
            from gcrm.tools.db_account_lifecycle import create_password_reset_token
            create_password_reset_token(7, "raw-token")
        sql, params = cur.execute.call_args.args
        assert "password_reset_tokens" in sql
        assert params[0] == 7
        assert params[1] != "raw-token"  # stored hashed, never plaintext

    def test_consume_valid_token_returns_user_id(self):
        conn, cur = make_mock_conn(rows=[{"user_id": 7}])
        with patch("gcrm.tools.db_account_lifecycle.db") as mock_db:
            mock_db.return_value.__enter__.return_value = conn
            from gcrm.tools.db_account_lifecycle import consume_password_reset_token
            assert consume_password_reset_token("raw-token") == 7

    def test_consume_expired_or_used_token_returns_none(self):
        conn, cur = make_mock_conn(rows=[])
        with patch("gcrm.tools.db_account_lifecycle.db") as mock_db:
            mock_db.return_value.__enter__.return_value = conn
            from gcrm.tools.db_account_lifecycle import consume_password_reset_token
            assert consume_password_reset_token("stale") is None

    def test_valid_check_is_read_only(self):
        conn, cur = make_mock_conn(rows=[{"?column?": 1}])
        with patch("gcrm.tools.db_account_lifecycle.db") as mock_db:
            mock_db.return_value.__enter__.return_value = conn
            from gcrm.tools.db_account_lifecycle import password_reset_token_valid
            assert password_reset_token_valid("raw-token") is True
        assert "UPDATE" not in cur.execute.call_args.args[0].upper()


class TestRequestPasswordReset:
    def test_active_user_gets_emailed(self):
        with patch("gcrm.api.auth.get_user_by_email", return_value=active_user()), \
             patch("gcrm.api.auth.create_password_reset_token") as mcreate, \
             patch("gcrm.api.auth.send_email", return_value=True) as msend, \
             patch("gcrm.api.auth.APP_PUBLIC_URL", "https://engcrm.example.com"):
            auth.request_password_reset("A@B.com")
        assert mcreate.call_args.args[0] == 7
        to, subject, body = msend.call_args.args
        assert to == "a@b.com"
        assert "reset" in subject.lower()
        assert "https://engcrm.example.com/reset-password?token=" in body

    def test_unknown_email_sends_nothing(self):
        with patch("gcrm.api.auth.get_user_by_email", return_value=None), \
             patch("gcrm.api.auth.send_email") as msend:
            auth.request_password_reset("ghost@nowhere.com")
        msend.assert_not_called()

    def test_inactive_user_sends_nothing(self):
        inactive = {**active_user(), "is_active": False}
        with patch("gcrm.api.auth.get_user_by_email", return_value=inactive), \
             patch("gcrm.api.auth.send_email") as msend:
            auth.request_password_reset("a@b.com")
        msend.assert_not_called()


class TestCompletePasswordReset:
    def test_success(self):
        with patch("gcrm.api.auth.consume_password_reset_token", return_value=7), \
             patch("gcrm.api.auth.set_user_password_by_id", return_value=True) as mset:
            assert auth.complete_password_reset("raw-token", "a-long-enough-password") is True
        assert mset.call_args.args[0] == 7

    def test_short_password_rejected_without_consuming_token(self):
        with patch("gcrm.api.auth.consume_password_reset_token") as mconsume:
            assert auth.complete_password_reset("raw-token", "short") is False
        mconsume.assert_not_called()

    def test_invalid_token_returns_false(self):
        with patch("gcrm.api.auth.consume_password_reset_token", return_value=None):
            assert auth.complete_password_reset("bad-token", "a-long-enough-password") is False


class TestWebRoutes:
    def test_forgot_password_page_renders(self):
        r = client.get("/forgot-password")
        assert r.status_code == 200
        assert "Forgot your password?" in r.text

    def test_forgot_password_submit_always_shows_generic_message(self):
        with patch("gcrm.api.auth.request_password_reset") as mreq:
            r = client.post("/forgot-password", data={"email": "a@b.com"})
        assert r.status_code == 200
        # not "we've" — Jinja autoescapes the apostrophe to &#39; now that this
        # string is rendered via t() instead of hardcoded directly in the HTML
        assert "sent a link to reset your password" in r.text
        mreq.assert_called_once_with("a@b.com")

    def test_reset_password_page_valid_token_shows_form(self):
        with patch("gcrm.api.auth.password_reset_token_valid", return_value=True):
            r = client.get("/reset-password", params={"token": "good"})
        assert r.status_code == 200
        assert 'name="new_password"' in r.text

    def test_reset_password_page_invalid_token_shows_error(self):
        with patch("gcrm.api.auth.password_reset_token_valid", return_value=False):
            r = client.get("/reset-password", params={"token": "bad"})
        assert r.status_code == 200
        assert "invalid or has expired" in r.text

    def test_reset_password_page_no_token_shows_error(self):
        r = client.get("/reset-password")
        assert "invalid or has expired" in r.text

    def test_reset_password_submit_success_redirects_to_login(self):
        with patch("gcrm.api.auth.complete_password_reset", return_value=True):
            r = client.post(
                "/reset-password", data={"token": "good", "new_password": "a-long-enough-password"},
                follow_redirects=False,
            )
        assert r.status_code == 303
        assert r.headers["location"] == "/login?reset=success"

    def test_reset_password_submit_failure_shows_error(self):
        with patch("gcrm.api.auth.complete_password_reset", return_value=False):
            r = client.post("/reset-password", data={"token": "bad", "new_password": "x"})
        assert r.status_code == 400
        assert "invalid or has expired" in r.text

    def test_login_shows_reset_success_banner(self):
        r = client.get("/login?reset=success")
        assert "sign in with your new password" in r.text


class TestMobileResetRequest:
    def test_always_returns_ok(self):
        with patch("gcrm.api.routers.api_auth.request_password_reset") as mreq:
            r = client.post("/api/auth/reset-request", json={"email": "a@b.com"})
        assert r.status_code == 200
        assert r.json() == {"ok": True}
        mreq.assert_called_once_with("a@b.com")

    def test_missing_email_still_returns_ok(self):
        with patch("gcrm.api.routers.api_auth.request_password_reset"):
            r = client.post("/api/auth/reset-request", json={})
        assert r.status_code == 200
