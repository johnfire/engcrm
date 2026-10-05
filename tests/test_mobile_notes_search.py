"""Mobile endpoints for finding someone and for logging a meeting: GET /api/search and
the organization notes routes (add, transcribe, delete). DB mocked — no Postgres."""
import io
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import gcrm.api.main as main
from gcrm.api.jwt_auth import create_token

client = TestClient(main.app)
ADMIN = {"Authorization": f"Bearer {create_token('admin')}"}
VIEWER = {"Authorization": f"Bearer {create_token('viewer')}"}


def cursor_returning(*result_sets):
    cursor = MagicMock()
    cursor.fetchall.side_effect = list(result_sets)
    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn, cursor


class TestSearch:
    def run(self, q, orgs=(), people=(), identity=(None, None), headers=ADMIN):
        conn, cursor = cursor_returning(list(orgs), list(people))
        with patch("gcrm.api.routers.api_search.db") as mock_db, \
             patch("gcrm.api.routers.api_search._personal_identity", return_value=identity):
            mock_db.return_value.__enter__.return_value = conn
            response = client.get("/api/search", params={"q": q}, headers=headers)
        return response, cursor

    def test_finds_organizations_and_people(self):
        response, _ = self.run(
            "acme",
            orgs=[{"id": 1, "name": "Acme GmbH", "city": "Ulm", "linkedin_connection_count": 2}],
            people=[{"id": 9, "name": "Anna Roth", "company": "Acme GmbH"}])
        body = response.json()
        assert response.status_code == 200
        assert body["organizations"][0]["linkedin_connection_count"] == 2
        assert body["people"][0]["company"] == "Acme GmbH"

    @pytest.mark.parametrize("q", ["", " ", "a", "  x "])
    def test_too_short_a_query_returns_nothing_not_everything(self, q):
        conn_patch = patch("gcrm.api.routers.api_search.db")
        with conn_patch as mock_db:
            response = client.get("/api/search", params={"q": q}, headers=ADMIN)
        assert response.json() == {"query": q, "organizations": [], "people": []}
        mock_db.assert_not_called()

    def test_every_word_must_match_somewhere(self):
        _, cursor = self.run("anna roth")
        org_sql, org_params = cursor.execute.call_args_list[0].args
        assert org_sql.count("ILIKE %s ESCAPE '!'") >= 4  # (name|city) per word, plus ordering
        assert org_params[:4] == ["%anna%", "%anna%", "%roth%", "%roth%"]

    def test_the_search_words_are_parameters_never_part_of_the_sql(self):
        _, cursor = self.run("x'; DROP TABLE contacts; --")
        for call in cursor.execute.call_args_list:
            assert "DROP TABLE" not in call.args[0]

    def test_wildcards_typed_by_the_user_are_taken_literally(self):
        _, cursor = self.run("100%_off")
        params = cursor.execute.call_args_list[0].args[1]
        assert "%100!%!_off%" in params

    def test_only_four_words_are_used(self):
        _, cursor = self.run("a1 b2 c3 d4 e5 f6")
        params = cursor.execute.call_args_list[0].args[1]
        assert not any("e5" in str(p) for p in params)

    def test_a_name_starting_with_the_first_word_leads(self):
        _, cursor = self.run("roth")
        sql, params = cursor.execute.call_args_list[1].args
        assert "ORDER BY (p.name ILIKE %s ESCAPE '!') DESC" in sql and params[-1] == "roth%"

    def test_results_are_capped_and_deleted_records_are_excluded(self):
        _, cursor = self.run("acme")
        for call in cursor.execute.call_args_list:
            assert "LIMIT 15" in call.args[0] and "deleted_at IS NULL" in call.args[0]

    def test_a_personal_account_only_sees_its_own_workspace(self):
        _, cursor = self.run("acme", identity=(3, 7))
        for call in cursor.execute.call_args_list:
            assert "workspace_id = %s" in call.args[0] and 7 in call.args[1]

    def test_a_login_is_required(self):
        assert client.get("/api/search", params={"q": "acme"}).status_code in (401, 403)

    def test_any_signed_in_role_may_search(self):
        assert self.run("acme", headers=VIEWER)[0].status_code == 200


def patched_notes(exists=True, note_id=11, deleted=True):
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.return_value = {"?column?": 1} if exists else None
    return (patch("gcrm.api.routers.api_organizations.db", **{"return_value.__enter__.return_value": conn}),
            patch("gcrm.api.routers.api_organizations.log_meeting_note", return_value=note_id),
            patch("gcrm.api.routers.api_organizations.delete_meeting_note", return_value=deleted))


class TestOrganizationNotes:
    def add(self, body, headers=ADMIN, exists=True):
        db_p, log_p, del_p = patched_notes(exists)
        with db_p, log_p as log, del_p:
            response = client.post("/api/contacts/7/notes", json=body, headers=headers)
        return response, log

    def test_logs_a_note(self):
        response, log = self.add({"note": "  Met the owner, wants a demo  ", "method": "in_person"})
        assert response.status_code == 200 and response.json() == {"id": 11, "follow_up_date": None}
        log.assert_called_once_with(7, "in_person", "Met the owner, wants a demo", None, None, duration_minutes=None)

    def test_with_a_follow_up_date(self):
        when = (date.today() + timedelta(days=7)).isoformat()
        response, log = self.add({"note": "Call back", "follow_up_date": when, "follow_up_text": " send quote "})
        assert response.json()["follow_up_date"] == when
        log.assert_called_once_with(7, None, "Call back", date.fromisoformat(when), "send quote", duration_minutes=None)

    @pytest.mark.parametrize("body", [
        {"note": ""}, {"note": "   "},
        {"note": "x", "method": "carrier pigeon"},
        {"note": "x", "follow_up_date": "tomorrow"},
        {"note": "x", "follow_up_date": "2001-01-01"},
        {"note": "x", "follow_up_date": (date.today() + timedelta(days=4000)).isoformat()},
    ])
    def test_bad_input_is_refused_and_nothing_is_written(self, body):
        response, log = self.add(body)
        assert response.status_code == 400
        log.assert_not_called()

    def test_yesterday_is_accepted_for_time_zone_slack(self):
        when = (date.today() - timedelta(days=1)).isoformat()
        assert self.add({"note": "x", "follow_up_date": when})[0].status_code == 200

    def test_a_missing_organization_is_a_404(self):
        response, log = self.add({"note": "x"}, exists=False)
        assert response.status_code == 404
        log.assert_not_called()

    def test_only_the_admin_may_log_notes(self):
        response, log = self.add({"note": "x"}, headers=VIEWER)
        assert response.status_code == 403
        log.assert_not_called()

    def test_delete_removes_a_note(self):
        db_p, log_p, del_p = patched_notes()
        with db_p, log_p, del_p as delete:
            response = client.delete("/api/contacts/7/notes/11", headers=ADMIN)
        assert response.status_code == 204
        delete.assert_called_once_with(7, 11)

    def test_deleting_someone_elses_or_a_gone_note_is_a_404(self):
        db_p, log_p, del_p = patched_notes(deleted=False)
        with db_p, log_p, del_p:
            assert client.delete("/api/contacts/7/notes/99", headers=ADMIN).status_code == 404

    def test_transcribe_returns_text_and_stores_nothing(self):
        db_p, log_p, del_p = patched_notes()
        with db_p, log_p as log, del_p, patch("gcrm.api.transcribe_upload.transcribe", return_value="Met Anna"):
            response = client.post("/api/contacts/7/notes/transcribe", headers=ADMIN,
                                   files={"audio": ("note.m4a", io.BytesIO(b"voice"), "audio/m4a")})
        assert response.status_code == 200 and response.json() == {"transcript": "Met Anna"}
        log.assert_not_called()

    @pytest.mark.parametrize("failure,status", [(None, 422), (RuntimeError("down"), 502)])
    def test_transcribe_failures(self, failure, status):
        db_p, log_p, del_p = patched_notes()
        kwargs = {"side_effect": failure} if failure else {"return_value": ""}
        with db_p, log_p, del_p, patch("gcrm.api.transcribe_upload.transcribe", **kwargs):
            response = client.post("/api/contacts/7/notes/transcribe", headers=ADMIN,
                                   files={"audio": ("note.m4a", io.BytesIO(b"voice"), "audio/m4a")})
        assert response.status_code == status

    def test_an_empty_recording_is_refused(self):
        db_p, log_p, del_p = patched_notes()
        with db_p, log_p, del_p:
            response = client.post("/api/contacts/7/notes/transcribe", headers=ADMIN,
                                   files={"audio": ("note.m4a", io.BytesIO(b""), "audio/m4a")})
        assert response.status_code == 400


class TestMeetingNoteStorage:
    def run(self, fn, *args, rowcount=1):
        from gcrm.tools import db_interactions
        conn = MagicMock()
        cursor = conn.cursor.return_value
        cursor.fetchone.return_value = {"id": 5}
        cursor.rowcount = rowcount
        with patch("gcrm.tools.db_interactions.db") as mock_db, patch("gcrm.tools.db_interactions.log_audit"):
            mock_db.return_value.__enter__.return_value = conn
            result = getattr(db_interactions, fn)(*args)
        return result, cursor

    def test_a_note_is_an_interaction_dated_today_with_no_direction_and_no_status_change(self):
        note_id, cursor = self.run("log_meeting_note", 7, "in_person", "Met", date(2026, 11, 1), "send quote")
        assert note_id == 5
        sql, params = cursor.execute.call_args_list[0].args
        assert "CURRENT_DATE" in sql and "'note'" in sql and "direction" not in sql
        assert params == (7, "in_person", "Met", "send quote", date(2026, 11, 1), None)  # no typed duration
        touched = cursor.execute.call_args_list[1].args[0]
        assert "UPDATE contacts SET updated_at" in touched and "status" not in touched.replace("updated", "")

    def test_deleting_is_soft_and_scoped_to_the_organization(self):
        deleted, cursor = self.run("delete_meeting_note", 7, 5)
        sql = cursor.execute.call_args.args[0]
        assert deleted is True and "SET deleted_at = NOW()" in sql and "contact_id = %s" in sql
        assert self.run("delete_meeting_note", 7, 5, rowcount=0)[0] is False

    def test_deleted_notes_no_longer_appear_in_the_history(self):
        conn = MagicMock()
        conn.cursor.return_value.fetchall.return_value = []
        from gcrm.tools import db_interactions
        with patch("gcrm.tools.db_interactions.db") as mock_db:
            mock_db.return_value.__enter__.return_value = conn
            db_interactions.get_organization_interactions(7)
        assert "deleted_at IS NULL" in conn.cursor.return_value.execute.call_args.args[0]
