"""People: save_person dedup, card->person promotion mapping, the mobile
/api/people endpoints, and the web person detail/edit page. DB is mocked — runs
without Postgres."""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import gcrm.api.main as main
from gcrm.api.auth import require_admin, require_login
from gcrm.api.jwt_auth import create_token
from gcrm.tools import cards, db_people, db_people_interactions, email_extract

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

    def test_insert_sets_workspace_id_from_the_request_context(self):
        """Regression: save_person() used to omit workspace_id entirely, so every
        person ended up NULL-workspace and workspace-scoped checks (e.g.
        set_person_value_rating's contact/person match) could never succeed."""
        conn, cur = make_mock_conn()
        # no email, so only the name-dedup miss then INSERT ... RETURNING id
        cur.fetchone.side_effect = [None, {"id": 13}]
        with (
            patch("gcrm.tools.db_people.db") as mock_db,
            patch("gcrm.tools.db_people.get_workspace_id", return_value=5),
        ):
            mock_db.return_value.__enter__.return_value = conn
            db_people.save_person(name="Anna Roth")
        insert = cur.execute.call_args_list[-1]
        assert "workspace_id" in insert.args[0]
        assert "COALESCE" in insert.args[0]
        assert insert.args[1][-1] == 5


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
        with patch("gcrm.api.routers.people.get_person", return_value=PERSON_ROW), \
             patch("gcrm.api.routers.people.get_person_interactions", return_value=[]):
            resp = client.get("/people/3")
        assert resp.status_code == 200
        assert "Anna Roth" in resp.text
        assert "Kunstmesse Augsburg" in resp.text
        assert 'action="/people/3/edit"' in resp.text

    def test_detail_shows_notes(self, admin_web):
        entry = {"id": 1, "occurred_at": "2026-08-24T14:30:00+00:00", "method": "visit",
                  "note": "Loved the new series, wants a studio visit."}
        with patch("gcrm.api.routers.people.get_person", return_value=PERSON_ROW), \
             patch("gcrm.api.routers.people.get_person_interactions", return_value=[entry]):
            resp = client.get("/people/3")
        assert resp.status_code == 200
        assert "Loved the new series" in resp.text

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


class TestDbPeopleInteractions:
    def test_log_person_note_inserts_and_touches_person(self):
        conn, cur = make_mock_conn()
        cur.fetchone.return_value = {"id": 5}
        with patch("gcrm.tools.db_people_interactions.db") as mock_db, \
             patch("gcrm.tools.db_people_interactions.log_audit") as mlog:
            mock_db.return_value.__enter__.return_value = conn
            note_id = db_people_interactions.log_person_note(3, "visit", "Great chat about the new series.")
        assert note_id == 5
        insert = cur.execute.call_args_list[0]
        assert "INSERT INTO people_interactions" in insert.args[0]
        assert insert.args[1] == (3, "visit", "Great chat about the new series.")
        update = cur.execute.call_args_list[1]
        assert "UPDATE people SET updated_at" in update.args[0]
        mlog.assert_called_once()

    def test_get_person_interactions_excludes_deleted(self):
        conn, cur = make_mock_conn(rows=[
            {"id": 2, "occurred_at": None, "method": "call", "note": "Follow-up call."},
        ])
        with patch("gcrm.tools.db_people_interactions.db") as mock_db:
            mock_db.return_value.__enter__.return_value = conn
            entries = db_people_interactions.get_person_interactions(3)
        assert entries[0]["note"] == "Follow-up call."
        sql = cur.execute.call_args.args[0]
        assert "deleted_at IS NULL" in sql
        assert "ORDER BY occurred_at DESC" in sql

    def test_delete_person_interaction_soft_deletes(self):
        conn, cur = make_mock_conn()
        cur.rowcount = 1
        with patch("gcrm.tools.db_people_interactions.db") as mock_db, \
             patch("gcrm.tools.db_people_interactions.log_audit") as mlog:
            mock_db.return_value.__enter__.return_value = conn
            deleted = db_people_interactions.delete_person_interaction(3, 2)
        assert deleted is True
        sql = cur.execute.call_args.args[0]
        assert "SET deleted_at = NOW()" in sql
        mlog.assert_called_once()

    def test_delete_missing_returns_false(self):
        conn, cur = make_mock_conn()
        cur.rowcount = 0
        with patch("gcrm.tools.db_people_interactions.db") as mock_db, \
             patch("gcrm.tools.db_people_interactions.log_audit") as mlog:
            mock_db.return_value.__enter__.return_value = conn
            assert db_people_interactions.delete_person_interaction(3, 999) is False
        mlog.assert_not_called()


class TestPersonNotesWebRoutes:
    def test_transcribe_requires_auth(self):
        resp = client.post("/people/3/notes/transcribe", files={"audio": ("n.webm", b"\x00", "audio/webm")},
                            follow_redirects=False)
        assert resp.status_code == 307

    def test_transcribe_success(self, admin_web):
        with patch("gcrm.api.routers.people.get_person", return_value=PERSON_ROW), \
             patch("gcrm.api.routers.people.transcribe", return_value="Met Anna, follow up next week"):
            resp = client.post("/people/3/notes/transcribe",
                                files={"audio": ("n.webm", b"\x00\x01", "audio/webm")})
        assert resp.status_code == 200
        assert resp.json()["transcript"] == "Met Anna, follow up next week"

    def test_transcribe_empty_result_is_422(self, admin_web):
        with patch("gcrm.api.routers.people.get_person", return_value=PERSON_ROW), \
             patch("gcrm.api.routers.people.transcribe", return_value=""):
            resp = client.post("/people/3/notes/transcribe",
                                files={"audio": ("n.webm", b"\x00\x01", "audio/webm")})
        assert resp.status_code == 422

    def test_transcribe_service_down_is_502(self, admin_web):
        with patch("gcrm.api.routers.people.get_person", return_value=PERSON_ROW), \
             patch("gcrm.api.routers.people.transcribe", side_effect=RuntimeError("boom")):
            resp = client.post("/people/3/notes/transcribe",
                                files={"audio": ("n.webm", b"\x00\x01", "audio/webm")})
        assert resp.status_code == 502

    def test_add_note_saves_and_redirects(self, admin_web):
        with patch("gcrm.api.routers.people.get_person", return_value=PERSON_ROW), \
             patch("gcrm.api.routers.people.log_person_note", return_value=9) as mlog:
            resp = client.post("/people/3/notes", data={"note": "Great visit", "method": "visit"},
                                follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"] == "/people/3?saved=1"
        mlog.assert_called_once_with(3, "visit", "Great visit")

    def test_add_note_rejects_blank(self, admin_web):
        with patch("gcrm.api.routers.people.get_person", return_value=PERSON_ROW), \
             patch("gcrm.api.routers.people.log_person_note") as mlog:
            resp = client.post("/people/3/notes", data={"note": "   "}, follow_redirects=False)
        assert resp.status_code == 400
        mlog.assert_not_called()

    def test_delete_note_redirects(self, admin_web):
        with patch("gcrm.api.routers.people.delete_person_interaction", return_value=True):
            resp = client.post("/people/3/notes/9/delete", follow_redirects=False)
        assert resp.status_code == 303

    def test_delete_note_404_when_missing(self, admin_web):
        with patch("gcrm.api.routers.people.delete_person_interaction", return_value=False):
            resp = client.post("/people/3/notes/9/delete", follow_redirects=False)
        assert resp.status_code == 404


class TestPersonNotesMobileRoutes:
    def test_list_requires_auth(self):
        assert client.get("/api/people/3/notes").status_code in (401, 403)

    def test_list_notes(self):
        entry = {"id": 1, "occurred_at": "2026-08-24T14:30:00+00:00", "method": "visit", "note": "Great visit"}
        with patch("gcrm.api.routers.api_people_interactions.get_person", return_value=PERSON_ROW), \
             patch("gcrm.api.routers.api_people_interactions.get_person_interactions", return_value=[entry]):
            resp = client.get("/api/people/3/notes", headers=AUTH)
        assert resp.status_code == 200
        assert resp.json()[0]["note"] == "Great visit"

    def test_list_404_when_person_missing(self):
        with patch("gcrm.api.routers.api_people_interactions.get_person", return_value=None):
            resp = client.get("/api/people/999/notes", headers=AUTH)
        assert resp.status_code == 404

    def test_transcribe_success(self):
        with patch("gcrm.api.routers.api_people_interactions.get_person", return_value=PERSON_ROW), \
             patch("gcrm.api.routers.api_people_interactions.transcribe", return_value="Met Anna"):
            resp = client.post("/api/people/3/notes/transcribe", headers=AUTH,
                                files={"audio": ("n.m4a", b"\x00\x01", "audio/m4a")})
        assert resp.status_code == 200
        assert resp.json()["transcript"] == "Met Anna"

    def test_add_note(self):
        with patch("gcrm.api.routers.api_people_interactions.get_person", return_value=PERSON_ROW), \
             patch("gcrm.api.routers.api_people_interactions.log_person_note", return_value=9) as mlog:
            resp = client.post("/api/people/3/notes", headers=AUTH,
                                json={"note": "Great visit", "method": "visit"})
        assert resp.status_code == 200
        assert resp.json()["id"] == 9
        mlog.assert_called_once_with(3, "visit", "Great visit")

    def test_add_note_rejects_blank(self):
        with patch("gcrm.api.routers.api_people_interactions.get_person", return_value=PERSON_ROW), \
             patch("gcrm.api.routers.api_people_interactions.log_person_note") as mlog:
            resp = client.post("/api/people/3/notes", headers=AUTH, json={"note": "   "})
        assert resp.status_code == 400
        mlog.assert_not_called()

    def test_delete_note(self):
        with patch("gcrm.api.routers.api_people_interactions.delete_person_interaction", return_value=True):
            resp = client.delete("/api/people/3/notes/9", headers=AUTH)
        assert resp.status_code == 200

    def test_delete_note_404_when_missing(self):
        with patch("gcrm.api.routers.api_people_interactions.delete_person_interaction", return_value=False):
            resp = client.delete("/api/people/3/notes/9", headers=AUTH)
        assert resp.status_code == 404


class TestGetPeopleFilters:
    """company_priority / value_rating filters on get_people — mirrors how
    organizations.py filters by personal_priority."""

    def test_no_filters_means_no_where_clause(self):
        # last_contact is itself a correlated subquery containing "WHERE", so
        # check for the query's own top-level filter clause specifically,
        # not just the substring "WHERE" (which the subquery always has).
        conn, cur = make_mock_conn([])
        with patch("gcrm.tools.db_people.db") as mock_db:
            mock_db.return_value.__enter__.return_value = conn
            db_people.get_people(user_id=7)
        sql, params = cur.execute.call_args.args
        assert "priority = %s" not in sql and "priority IS NULL" not in sql
        assert "person.name ILIKE" not in sql
        assert params == [7, 7]  # the two rating-join user_id params only

    def test_company_priority_filters_by_exact_value(self):
        conn, cur = make_mock_conn([])
        with patch("gcrm.tools.db_people.db") as mock_db:
            mock_db.return_value.__enter__.return_value = conn
            db_people.get_people(user_id=7, company_priority="3")
        sql, params = cur.execute.call_args.args
        assert "company_priority.priority = %s" in sql
        assert params == [7, 7, 3]

    def test_value_rating_unrated_filters_on_null(self):
        conn, cur = make_mock_conn([])
        with patch("gcrm.tools.db_people.db") as mock_db:
            mock_db.return_value.__enter__.return_value = conn
            db_people.get_people(user_id=7, value_rating="unrated")
        sql, params = cur.execute.call_args.args
        assert "person_priority.priority IS NULL" in sql
        assert params == [7, 7]

    def test_search_and_rating_filters_combine_with_and(self):
        conn, cur = make_mock_conn([])
        with patch("gcrm.tools.db_people.db") as mock_db:
            mock_db.return_value.__enter__.return_value = conn
            db_people.get_people("anna", user_id=7, company_priority="2", value_rating="unrated")
        sql, params = cur.execute.call_args.args
        assert " AND " in sql.split("WHERE", 1)[1]
        assert params == [7, 7, "%anna%", "%anna%", "%anna%", 2]

    def test_invalid_rating_value_is_ignored(self):
        conn, cur = make_mock_conn([])
        with patch("gcrm.tools.db_people.db") as mock_db:
            mock_db.return_value.__enter__.return_value = conn
            db_people.get_people(user_id=7, company_priority="not-a-rating")
        sql, params = cur.execute.call_args.args
        assert "priority = %s" not in sql and "priority IS NULL" not in sql
        assert params == [7, 7]
