"""History corrections, chronology, local day boundaries and workspace isolation."""
from datetime import date

import pytest
from fastapi import HTTPException

from gcrm.audit_context import audit_scope
from gcrm.db.connection import db
from gcrm.tools.db_contact_dates import get_contact_date, set_contact_date
from gcrm.tools.db_contact_feed import get_contact_feed

pytestmark = pytest.mark.integration


@pytest.fixture
def contact_records(clean_database):
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug='default'")
        workspace_id = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO contacts (name,workspace_id) VALUES ('Academy',%s) RETURNING id", (workspace_id,))
        organization_id = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO people (name,workspace_id) VALUES ('Ann',%s) RETURNING id", (workspace_id,))
        person_id = cursor.fetchone()["id"]
    return workspace_id, organization_id, person_id


@pytest.mark.parametrize("kind", ["organization", "person"])
def test_correcting_contact_updates_history_feed_and_audit(contact_records, kind):
    workspace_id, organization_id, person_id = contact_records
    contact_id = person_id if kind == "person" else organization_id
    assert get_contact_feed(workspace_id=workspace_id) == []
    with audit_scope("owner@example.test", "user", "date-correction"):
        recorded = set_contact_date(kind, contact_id, date(2026, 10, 4), None, None, workspace_id)
        corrected = set_contact_date(kind, contact_id, date(2026, 10, 2), recorded["interaction_id"], "2026-10-04", workspace_id)
    assert corrected["contact_date"] == "2026-10-02"
    assert get_contact_feed(workspace_id=workspace_id)[0]["last_contact"] == "2026-10-02"
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT COUNT(*) AS count FROM audit_log WHERE action='contact.date_changed' "
                       "AND actor='owner@example.test' AND actor_type='user' AND correlation_id='date-correction'")
        assert cursor.fetchone()["count"] == 2
        history = "people_interactions" if kind == "person" else "interactions"
        cursor.execute(f"SELECT COUNT(*) AS count FROM {history}")
        assert cursor.fetchone()["count"] == 1  # Correction does not invent a second event.
    with pytest.raises(HTTPException) as stale:
        set_contact_date(kind, contact_id, date(2026, 10, 1), recorded["interaction_id"], "2026-10-04", workspace_id)
    assert stale.value.status_code == 409


def test_feed_uses_contact_day_not_creation_day_and_ignores_plans_and_deleted_history(contact_records):
    workspace_id, organization_id, person_id = contact_records
    set_contact_date("person", person_id, date(2026, 10, 3), None, None, workspace_id)
    set_contact_date("organization", organization_id, date(2026, 10, 4), None, None, workspace_id)
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("UPDATE people SET created_at='2026-10-06'")
        cursor.execute("UPDATE contacts SET created_at='2020-01-01'")
        cursor.execute("INSERT INTO people_interactions (person_id,occurred_at,method,note) VALUES "
                       "(%s,'2026-10-06','next_step','Plan'),(%s,'2026-10-06','next_step_done','Done')", (person_id, person_id))
        cursor.execute("INSERT INTO people_interactions (person_id,occurred_at,method,note,deleted_at) "
                       "VALUES (%s,'2026-10-06','call','Deleted',NOW())", (person_id,))
    contacts = get_contact_feed(workspace_id=workspace_id)
    assert [(contact["kind"], contact["last_contact"]) for contact in contacts] == [
        ("organization", "2026-10-04"), ("person", "2026-10-03"),
    ]
    assert get_contact_feed(workspace_id=workspace_id, sort="newest") == contacts  # Old app sort alias.


def test_local_midnight_and_backdating_past_another_event(contact_records):
    workspace_id, _, person_id = contact_records
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("INSERT INTO people_interactions (person_id,occurred_at,method,note) VALUES "
                       "(%s,'2026-10-03T22:30:00Z','call','After midnight'),"
                       "(%s,'2026-10-03T09:00:00Z','visit','Earlier')", (person_id, person_id))
    current = get_contact_date("person", person_id, workspace_id)
    assert current["contact_date"] == "2026-10-04"
    updated = set_contact_date("person", person_id, date(2026, 10, 2), current["interaction_id"], "2026-10-04", workspace_id)
    assert updated["contact_date"] == "2026-10-03"  # The other actual contact is now latest.
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT occurred_at AT TIME ZONE 'Europe/Berlin' AS local_time, created_at FROM people_interactions WHERE id=%s",
                       (current["interaction_id"],))
        recorded = cursor.fetchone()
        assert recorded["local_time"].isoformat() == "2026-10-02T00:30:00"


def test_missing_deleted_and_other_workspace_records_are_not_editable(contact_records):
    workspace_id, organization_id, person_id = contact_records
    for kind, contact_id in [("person", person_id), ("organization", organization_id)]:
        for foreign_workspace in (workspace_id + 100,):
            with pytest.raises(HTTPException) as hidden:
                get_contact_date(kind, contact_id, foreign_workspace)
            assert hidden.value.status_code == 404
            with pytest.raises(HTTPException) as unwritable:
                set_contact_date(kind, contact_id, date(2026, 10, 2), None, None, foreign_workspace)
            assert unwritable.value.status_code == 404
    with db() as connection:
        connection.cursor().execute("UPDATE contacts SET deleted_at=NOW() WHERE id=%s", (organization_id,))
    with pytest.raises(HTTPException):
        get_contact_date("organization", organization_id, workspace_id)
    with pytest.raises(HTTPException):
        get_contact_date("person", person_id + 100, workspace_id)
