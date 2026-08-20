"""i18n: the translate() engine, the new /api/auth/me, PATCH /api/account/language,
POST /settings/language endpoints, and the ?lang= pre-login toggle. DB and push
are mocked — these run without Postgres or a live Expo push service."""
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

import gcrm.api.main as main
from gcrm.api.jwt_auth import create_token
from gcrm.i18n import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES, translate

client = TestClient(main.app)
AUTH = {"Authorization": f"Bearer {create_token('admin', user_id=7, token_version=0)}"}


def make_mock_conn(rows=None):
    cur = MagicMock()
    cur.fetchone.return_value = rows[0] if rows else None
    cur.fetchall.return_value = rows or []
    conn = MagicMock()
    conn.cursor.return_value = cur
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    return conn, cur


class TestTranslateEngine:
    def test_resolves_key_per_language(self):
        assert translate("nav.contacts", "en") == "Organizations"
        assert translate("nav.contacts", "de") == "Organisationen"
        assert translate("personalPriority.title", "en") == "Personal priority"
        assert translate("personalPriority.title", "de") == "Persönliche Priorität"

    def test_interpolation(self):
        assert translate("organizations.deleteConfirm", "en", name="Acme") == "Delete Acme?"
        assert translate("organizations.deleteConfirm", "de", name="Acme") == "Acme löschen?"

    def test_pluralization_one_vs_other(self):
        assert translate("drafts.onHold", "en", count=1) == "1 email on hold"
        assert translate("drafts.onHold", "en", count=3) == "3 emails on hold"

    def test_falls_back_to_english_when_missing_in_language(self):
        with patch.dict("gcrm.i18n.translate._catalogs", {"de": {}}, clear=False):
            assert translate("nav.contacts", "de") == "Organizations"

    def test_missing_key_shows_visible_marker(self):
        assert translate("totally.made.up.key", "en") == "[totally.made.up.key]"

    def test_default_language_is_english(self):
        assert DEFAULT_LANGUAGE == "en"
        assert SUPPORTED_LANGUAGES == ("en", "de")


class TestAuthMe:
    def test_requires_auth(self):
        assert client.get("/api/auth/me").status_code in (401, 403)

    def test_returns_account_language(self):
        user_row = {"id": 7, "email": "a@b.com", "role": "admin", "ui_language": "de"}
        with patch("gcrm.api.routers.api_auth.get_user_by_id", return_value=user_row):
            r = client.get("/api/auth/me", headers=AUTH)
        assert r.status_code == 200
        assert r.json() == {"email": "a@b.com", "role": "admin", "ui_language": "de"}

    def test_missing_account_is_401(self):
        with patch("gcrm.api.routers.api_auth.get_user_by_id", return_value=None):
            r = client.get("/api/auth/me", headers=AUTH)
        assert r.status_code == 401

    def test_shared_admin_defaults_to_english(self):
        token = create_token("admin")  # no user_id -> break-glass shape
        r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert r.json() == {"email": "shared-admin", "role": "admin", "ui_language": "en"}


class TestUpdateLanguage:
    def test_requires_auth(self):
        assert client.patch("/api/account/language", json={"ui_language": "de"}).status_code in (401, 403)

    def test_rejects_unsupported_language(self):
        r = client.patch("/api/account/language", headers=AUTH, json={"ui_language": "fr"})
        assert r.status_code == 400

    def test_updates_and_sends_silent_push(self):
        with patch("gcrm.api.routers.api_account.set_user_ui_language", return_value=True) as mset, \
             patch("gcrm.api.routers.api_account.send_silent_push_to_user") as mpush:
            r = client.patch("/api/account/language", headers=AUTH, json={"ui_language": "de"})
        assert r.status_code == 200
        assert r.json() == {"ui_language": "de"}
        assert mset.call_args.args == (7, "de")
        assert mpush.call_args.args[0] == 7
        assert mpush.call_args.args[1]["type"] == "ui_language_changed"

    def test_shared_admin_cannot_update(self):
        token = create_token("admin")
        r = client.patch(
            "/api/account/language", headers={"Authorization": f"Bearer {token}"}, json={"ui_language": "de"},
        )
        assert r.status_code == 400

    def test_unknown_account_is_404(self):
        with patch("gcrm.api.routers.api_account.set_user_ui_language", return_value=False):
            r = client.patch("/api/account/language", headers=AUTH, json={"ui_language": "de"})
        assert r.status_code == 404


class TestWebSettingsLanguage:
    def test_requires_login(self):
        r = client.post("/settings/language", data={"ui_language": "de"}, follow_redirects=False)
        assert r.status_code in (303, 307)

    def test_rejects_unsupported_language(self):
        from gcrm.api.auth import require_login
        main.app.dependency_overrides[require_login] = lambda: "admin"
        try:
            r = client.post("/settings/language", data={"ui_language": "fr"})
            assert r.status_code == 400
        finally:
            main.app.dependency_overrides.pop(require_login, None)


class TestPreLoginLangToggle:
    def test_lang_query_param_sets_session_and_persists_across_requests(self):
        r = client.get("/login?lang=de")
        assert r.status_code == 200
        assert "Passwort" in r.text  # login.passwordPlaceholder in German
        # session cookie carries the choice forward without ?lang= on the next request
        r2 = client.get("/login")
        assert "Passwort" in r2.text

    def test_invalid_lang_value_ignored(self):
        r = client.get("/login?lang=fr")
        assert r.status_code == 200  # doesn't crash; falls back to whatever was already set

    def test_login_error_message_respects_session_language(self):
        r = client.get("/login?lang=de")
        assert r.status_code == 200
        with patch("gcrm.api.auth._lookup_user", return_value=None):
            r = client.post("/login", data={"email": "x@y.com", "password": "wrong"})
        assert "E-Mail oder Passwort ungültig" in r.text
        # reset session language back to English so later tests in this process aren't affected
        client.get("/login?lang=en")


class TestCatalogPathTraversal:
    """_load_catalog() builds a filesystem path from the language. main.py
    validates ?lang= on the way in, but the guard has to live where the path is
    built too — otherwise one future caller passing a raw value turns a
    translation lookup into an arbitrary file read."""

    def test_traversal_language_falls_back_to_default(self):
        assert translate("nav.contacts", "../../../../etc/passwd") == translate("nav.contacts", DEFAULT_LANGUAGE)

    def test_unsupported_language_falls_back_to_default(self):
        assert translate("nav.contacts", "fr") == translate("nav.contacts", DEFAULT_LANGUAGE)

    def test_supported_languages_still_resolve_independently(self):
        rendered = {language: translate("nav.contacts", language) for language in SUPPORTED_LANGUAGES}
        assert all(value and not value.startswith("[") for value in rendered.values())
