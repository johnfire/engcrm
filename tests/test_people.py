"""People: save_person dedup, card->person promotion mapping, the mobile
/api/people endpoints, and the web person detail/edit page. DB is mocked — runs
without Postgres."""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import gcrm.api.main as main
from gcrm.api.auth import require_admin, require_login
from gcrm.api.jwt_auth import create_token
from gcrm.tools import cards, db_people, email_extract

client = TestClient(main.app)
AUTH = {"Authorization": f"Bearer {create_token('admin')}"}


def make_mock_conn(rows=None):
    cur = MagicMock()
    cur.fetchone.return_value = rows[0] if rows else None
    cur.fetchall.return_value = rows or []
    conn = MagicMock()
    conn.cursor.return_value = cur
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    return conn, cur


class TestSavePerson:
    def test_inserts_when_new(self):
        conn, cur = make_mock_conn()
        # email-dedup miss, name-dedup miss, then INSERT ... RETURNING id
        cur.fetchone.side_effect = [None, None, {"id": 11}]
        with patch("gcrm.tools.db_people.db") as mock_db:
            mock_db.return_value.__enter__.return_value = conn
            person_id = db_people.save_person(name="Anna Roth", email="anna@acme.de", contact_id=42)
        assert person_id == 11
        assert "INSERT INTO people" in cur.execute.call_args_list[-1].args[0]

    def test_stores_met_at(self):
        conn, cur = make_mock_conn()
        # no email, so only the name-dedup miss then INSERT ... RETURNING id
        cur.fetchone.side_effect = [None, {"id": 12}]
        with patch("gcrm.tools.db_people.db") as mock_db:
            mock_db.return_value.__enter__.return_value = conn
            db_people.save_person(name="Anna Roth", met_at="Kunstmesse Augsburg")
        insert = cur.execute.call_args_list[-1]
        assert "met_at" in insert.args[0]
        assert "Kunstmesse Augsburg" in insert.args[1]

    def test_dedups_on_email(self):
        conn, cur = make_mock_conn()
        cur.fetchone.side_effect = [{"id": 7}]  # email match on first lookup
        with patch("gcrm.tools.db_people.db") as mock_db:
            mock_db.return_value.__enter__.return_value = conn
            person_id = db_people.save_person(name="Anna", email="anna@acme.de")
        assert person_id == 7
        assert all(
            "INSERT" not in (call.args[0] if call.args else "")
            for call in cur.execute.call_args_list
        )


class TestMetAtOnRescan:
    """A re-scan deduping onto an existing person must still record the new
    place — but an empty field must never wipe the place already stored."""

    def test_updates_met_at_on_dedup_hit(self):
        conn, cur = make_mock_conn()
        cur.fetchone.side_effect = [{"id": 7}]  # email match
        with patch("gcrm.tools.db_people.db") as mock_db:
            mock_db.return_value.__enter__.return_value = conn
            person_id = db_people.save_person(
                name="Anna", email="anna@acme.de", met_at="Gallery opening",
            )
        assert person_id == 7
        update = cur.execute.call_args_list[-1]
        assert "UPDATE people SET met_at" in update.args[0]
        assert update.args[1] == ("Gallery opening", 7)

    def test_empty_met_at_does_not_clear(self):
        conn, cur = make_mock_conn()
        cur.fetchone.side_effect = [{"id": 7}]
        with patch("gcrm.tools.db_people.db") as mock_db:
            mock_db.return_value.__enter__.return_value = conn
            person_id = db_people.save_person(name="Anna", email="anna@acme.de")
        assert person_id == 7
        assert all(
            "UPDATE" not in (call.args[0] if call.args else "")
            for call in cur.execute.call_args_list
        )


class TestPromoteToPerson:
    def test_maps_card_fields(self):
        with patch("gcrm.tools.db.save_person", return_value=11) as msave:
            person_id = cards.promote_to_person(
                {"name": "Anna Roth", "title": "CTO", "email": "anna@acme.de",
                 "phone": "+49 821 1", "city": "Augsburg", "country": "DE",
                 "met_at": " Kunstmesse Augsburg "},
                contact_id=42,
            )
        assert person_id == 11
        assert msave.call_args.kwargs["name"] == "Anna Roth"
        assert msave.call_args.kwargs["title"] == "CTO"
        assert msave.call_args.kwargs["met_at"] == "Kunstmesse Augsburg"
        assert msave.call_args.kwargs["contact_id"] == 42
        assert msave.call_args.kwargs["source"] == "card_capture"

    def test_no_name_skips(self):
        with patch("gcrm.tools.db.save_person") as msave:
            assert cards.promote_to_person({"company": "ACME"}, contact_id=1) == 0
        msave.assert_not_called()


class TestEmailExtraction:
    def test_extract_parses_and_costs(self):
        resp = MagicMock()
        resp.content = '{"name": "Anna Roth", "email": "anna@acme.de", "company": "ACME"}'
        resp.usage_metadata = {"input_tokens": 1000, "output_tokens": 100}
        fake_llm = MagicMock()
        fake_llm.invoke.return_value = resp
        with patch("gcrm.tools.llm.get_llm", return_value=fake_llm):
            out = email_extract.extract_person_from_email("From: Anna Roth <anna@acme.de>")
        assert out["fields"]["name"] == "Anna Roth"
        assert out["model"] == "claude-haiku-4-5-20251001"
        # (1000*0.80 + 100*4.00) / 1e6 = 0.0012
        assert abs(out["cost_usd"] - 0.0012) < 1e-6

    def test_extract_handles_failure(self):
        fake_llm = MagicMock()
        fake_llm.invoke.side_effect = RuntimeError("boom")
        with patch("gcrm.tools.llm.get_llm", return_value=fake_llm):
            out = email_extract.extract_person_from_email("some text")
        assert out["cost_usd"] == 0.0
        # The upstream message is logged, never handed to the client.
        assert out["fields"]["error"] == email_extract._EXTRACTION_FAILED
        assert "boom" not in out["fields"]["error"]


class TestPeopleEndpoint:
    def test_requires_auth(self):
        assert client.get("/api/people").status_code in (401, 403)

    def test_list(self):
        with patch("gcrm.api.routers.api_people.get_people",
                   return_value=[{"id": 1, "name": "Anna", "company": "ACME"}]):
            resp = client.get("/api/people", headers=AUTH)
        assert resp.status_code == 200
        assert resp.json()[0]["name"] == "Anna"

    def test_detail_404(self):
        with patch("gcrm.api.routers.api_people.get_person", return_value=None):
            resp = client.get("/api/people/999", headers=AUTH)
        assert resp.status_code == 404


PERSON_ROW = {
    "id": 3, "name": "Anna Roth", "title": "Kuratorin", "email": "anna@galerie-nord.de",
    "phone": "+49 821 555 12", "website": None, "city": "Augsburg", "country": "DE",
    "relationship": None, "notes": "Met at the spring fair.", "met_at": "Kunstmesse Augsburg",
    "contact_id": 42, "company": "Galerie Nord", "source": "card_capture",
    "created_at": "2026-08-19T10:00:00+00:00",
}


@pytest.fixture
def admin_web():
    main.app.dependency_overrides[require_login] = lambda: "admin"
    main.app.dependency_overrides[require_admin] = lambda: "admin"
    yield
    main.app.dependency_overrides.pop(require_login, None)
    main.app.dependency_overrides.pop(require_admin, None)


class TestUpdatePerson:
    def test_writes_only_whitelisted_columns(self):
        conn, cur = make_mock_conn()
        cur.rowcount = 1
        with patch("gcrm.tools.db_people.db") as mock_db:
            mock_db.return_value.__enter__.return_value = conn
            ok = db_people.update_person(3, {
                "name": "Anna Roth", "met_at": "Gallery opening",
                # Neither is editable: a form must not be able to reassign the
                # company link or rewrite provenance.
                "contact_id": 99, "source": "forged",
            })
        assert ok is True
        sql = cur.execute.call_args.args[0]
        assert "name = %s" in sql and "met_at = %s" in sql
        assert "contact_id" not in sql and "source" not in sql

    def test_blank_becomes_null(self):
        conn, cur = make_mock_conn()
        cur.rowcount = 1
        with patch("gcrm.tools.db_people.db") as mock_db:
            mock_db.return_value.__enter__.return_value = conn
            db_people.update_person(3, {"name": "Anna", "phone": "   "})
        assert None in cur.execute.call_args.args[1]

    def test_missing_person_returns_false(self):
        conn, cur = make_mock_conn()
        cur.rowcount = 0
        with patch("gcrm.tools.db_people.db") as mock_db:
            mock_db.return_value.__enter__.return_value = conn
            assert db_people.update_person(999, {"name": "Ghost"}) is False


class TestPersonDetailPage:
    def test_detail_renders(self, admin_web):
        with patch("gcrm.api.routers.people.get_person", return_value=PERSON_ROW):
            resp = client.get("/people/3")
        assert resp.status_code == 200
        assert "Anna Roth" in resp.text
        assert "Kunstmesse Augsburg" in resp.text
        assert 'action="/people/3/edit"' in resp.text

    def test_detail_404(self, admin_web):
        with patch("gcrm.api.routers.people.get_person", return_value=None):
            assert client.get("/people/999").status_code == 404

    def test_edit_saves_and_redirects(self, admin_web):
        with patch("gcrm.api.routers.people.update_person", return_value=True) as update, \
             patch("gcrm.api.routers.people.log_audit"):
            resp = client.post(
                "/people/3/edit",
                data={"name": "Anna Roth", "met_at": "Gallery opening", "notes": "x"},
                follow_redirects=False,
            )
        assert resp.status_code == 303
        assert resp.headers["location"] == "/people/3?saved=1"
        assert update.call_args.args[1]["met_at"] == "Gallery opening"

    def test_edit_rejects_blank_name(self, admin_web):
        with patch("gcrm.api.routers.people.update_person") as update:
            resp = client.post("/people/3/edit", data={"name": "  "}, follow_redirects=False)
        assert resp.status_code == 400
        update.assert_not_called()

    def test_edit_404_when_missing(self, admin_web):
        with patch("gcrm.api.routers.people.update_person", return_value=False):
            resp = client.post("/people/3/edit", data={"name": "Ghost"}, follow_redirects=False)
        assert resp.status_code == 404


class TestExtractEmailEndpoint:
    def test_requires_auth(self):
        resp = client.post("/people/extract-email", json={"text": "hi"}, follow_redirects=False)
        assert resp.status_code == 307

    def test_blank_text_rejected(self, admin_web):
        resp = client.post("/people/extract-email", json={"text": "  "})
        assert resp.status_code == 400

    def test_success_returns_fields(self, admin_web):
        with patch(
            "gcrm.api.routers.people.extract_person_from_email",
            return_value={"fields": {"name": "Anna Roth", "email": "anna@acme.de"}},
        ):
            resp = client.post("/people/extract-email", json={"text": "From: Anna Roth"})
        assert resp.status_code == 200
        assert resp.json()["fields"]["name"] == "Anna Roth"

    def test_extraction_failure_surfaces_fixed_string(self, admin_web):
        with patch(
            "gcrm.api.routers.people.extract_person_from_email",
            return_value={"fields": {"error": email_extract._EXTRACTION_FAILED}},
        ):
            resp = client.post("/people/extract-email", json={"text": "garbled text"})
        assert resp.status_code == 200
        assert resp.json()["fields"]["error"] == email_extract._EXTRACTION_FAILED


class TestPersonNewPage:
    def test_form_renders(self, admin_web):
        resp = client.get("/people/new")
        assert resp.status_code == 200
        assert 'action="/people/new"' in resp.text

    def test_create_saves_and_redirects(self, admin_web):
        with patch("gcrm.api.routers.people.save_person", return_value=42) as msave, \
             patch("gcrm.api.routers.people.log_audit"):
            resp = client.post(
                "/people/new",
                data={"name": "Anna Roth", "email": "anna@acme.de"},
                follow_redirects=False,
            )
        assert resp.status_code == 303
        assert resp.headers["location"] == "/people/42?saved=1"
        assert msave.call_args.kwargs["name"] == "Anna Roth"
        assert msave.call_args.kwargs["source"] == "manual"

    def test_create_rejects_blank_name(self, admin_web):
        with patch("gcrm.api.routers.people.save_person") as msave:
            resp = client.post("/people/new", data={"name": "  "}, follow_redirects=False)
        assert resp.status_code == 400
        msave.assert_not_called()
