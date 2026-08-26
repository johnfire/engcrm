"""Held drafts (approval_queue, status=on_hold) target either an organization
(contact_id) or a person (person_id) — see
gcrm/db/migrations/045_approval_queue_person_target.sql and
docs/plans/2026-08-26-person-curiosity-email-design.md. DB is mocked — runs
without Postgres."""
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import gcrm.api.main as main
from gcrm.api.auth import require_admin, require_login
from gcrm.tools import db_approvals

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


@pytest.fixture
def admin_web():
    main.app.dependency_overrides[require_login] = lambda: "admin"
    main.app.dependency_overrides[require_admin] = lambda: "admin"
    yield
    main.app.dependency_overrides.pop(require_login, None)
    main.app.dependency_overrides.pop(require_admin, None)


class TestQueuePersonDraft:
    def test_inserts_on_hold_with_person_id(self):
        conn, cur = make_mock_conn([{"id": 9}])
        with patch("gcrm.tools.db_approvals.db") as mock_db, \
             patch("gcrm.tools.db_approvals.log_audit"):
            mock_db.return_value.__enter__.return_value = conn
            draft_id = db_approvals.queue_person_draft(3, "Subject", "Body")
        assert draft_id == 9
        sql, params = cur.execute.call_args.args
        assert "person_id" in sql and "'on_hold'" in sql
        assert params == (3, "Subject", "Body")


PERSON_DRAFT_ROW = {
    "draft_subject": "Curious how you see AI affecting your work",
    "draft_body": "original body",
    "contact_id": None,
    "person_id": 3,
    "email": "anna@example.com",
    "created_at": datetime.now(),
}
ORG_DRAFT_ROW = {
    "draft_subject": "Let's talk Digitalisierung",
    "draft_body": "original body",
    "contact_id": 42,
    "person_id": None,
    "email": "info@acme.de",
    "created_at": datetime.now(),
}


class TestDraftDetailPage:
    def test_404_when_not_on_hold(self, admin_web):
        conn, cur = make_mock_conn([])
        with patch("gcrm.api.routers.drafts.db") as mock_db:
            mock_db.return_value.__enter__.return_value = conn
            resp = client.get("/drafts/999")
        assert resp.status_code == 404

    def test_renders_person_targeted_draft(self, admin_web):
        row = {"id": 5, "draft_subject": "Hi", "draft_body": "Body text", "created_at": __import__("datetime").datetime.now(),
               "reviewer_note": None, "contact_id": None, "person_id": 3,
               "recipient_name": "Anna Roth", "email": "anna@example.com", "city": "Augsburg"}
        conn, cur = make_mock_conn([row])
        with patch("gcrm.api.routers.drafts.db") as mock_db:
            mock_db.return_value.__enter__.return_value = conn
            resp = client.get("/drafts/5")
        assert resp.status_code == 200
        assert "Anna Roth" in resp.text
        assert "/people/3" in resp.text
        assert 'action="/drafts/5/approve"' in resp.text


class TestDraftApprove:
    def test_person_targeted_sends_and_logs_person_note_not_interaction(self, admin_web):
        conn, cur = make_mock_conn([PERSON_DRAFT_ROW])
        with patch("gcrm.api.routers.drafts.db") as mock_db, \
             patch("gcrm.tools.email.send_email", return_value=True) as send, \
             patch("gcrm.tools.db_people_interactions.log_person_note") as log_note, \
             patch("gcrm.tools.db.log_interaction") as log_interaction, \
             patch("gcrm.api.routers.drafts.log_audit"):
            mock_db.return_value.__enter__.return_value = conn
            resp = client.post("/drafts/5/approve", data={}, headers={"HX-Request": "true"})
        assert resp.status_code == 200
        send.assert_called_once_with(to_email="anna@example.com", subject=PERSON_DRAFT_ROW["draft_subject"], body=PERSON_DRAFT_ROW["draft_body"])
        log_note.assert_called_once_with(3, "email", f"Sent: {PERSON_DRAFT_ROW['draft_subject']}")
        log_interaction.assert_not_called()

    def test_org_targeted_sends_and_logs_interaction_not_person_note(self, admin_web):
        conn, cur = make_mock_conn([ORG_DRAFT_ROW])
        with patch("gcrm.api.routers.drafts.db") as mock_db, \
             patch("gcrm.tools.email.send_email", return_value=True) as send, \
             patch("gcrm.tools.db.log_interaction") as log_interaction, \
             patch("gcrm.tools.db_people_interactions.log_person_note") as log_note, \
             patch("gcrm.api.routers.drafts.log_audit"):
            mock_db.return_value.__enter__.return_value = conn
            resp = client.post("/drafts/5/approve", data={}, headers={"HX-Request": "true"})
        assert resp.status_code == 200
        send.assert_called_once_with(to_email="info@acme.de", subject=ORG_DRAFT_ROW["draft_subject"], body=ORG_DRAFT_ROW["draft_body"])
        log_interaction.assert_called_once()
        assert log_interaction.call_args.kwargs["contact_id"] == 42
        log_note.assert_not_called()

    def test_edited_subject_and_body_from_full_page_editor_are_sent(self, admin_web):
        conn, cur = make_mock_conn([PERSON_DRAFT_ROW])
        with patch("gcrm.api.routers.drafts.db") as mock_db, \
             patch("gcrm.tools.email.send_email", return_value=True) as send, \
             patch("gcrm.tools.db_people_interactions.log_person_note"), \
             patch("gcrm.api.routers.drafts.log_audit"):
            mock_db.return_value.__enter__.return_value = conn
            client.post(
                "/drafts/5/approve",
                data={"final_subject": "Edited subject", "final_body": "Edited body"},
                headers={"HX-Request": "true"},
            )
        send.assert_called_once_with(to_email="anna@example.com", subject="Edited subject", body="Edited body")

    def test_htmx_request_gets_partial_plain_request_gets_redirect(self, admin_web):
        conn, cur = make_mock_conn([PERSON_DRAFT_ROW])
        with patch("gcrm.api.routers.drafts.db") as mock_db, \
             patch("gcrm.tools.email.send_email", return_value=True), \
             patch("gcrm.tools.db_people_interactions.log_person_note"), \
             patch("gcrm.api.routers.drafts.log_audit"):
            mock_db.return_value.__enter__.return_value = conn
            resp = client.post("/drafts/5/approve", data={}, follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"] == "/drafts/"

    def test_not_on_hold_is_404(self, admin_web):
        conn, cur = make_mock_conn([])
        with patch("gcrm.api.routers.drafts.db") as mock_db:
            mock_db.return_value.__enter__.return_value = conn
            resp = client.post("/drafts/999/approve", data={})
        assert resp.status_code == 404
