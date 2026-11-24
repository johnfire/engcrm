"""Legacy promises become reviewable tasks exactly once."""
from datetime import date
from pathlib import Path

import pytest

from gcrm.db.connection import db
from gcrm.tools.db_interactions import log_meeting_note
from gcrm.tools.db_organizations import save_organization
from gcrm.tools.deal_records import get_deals, set_deal_next_step
from gcrm.tools.follow_up_import import import_legacy_follow_ups
from gcrm.tools.follow_ups import list_follow_ups, resolve_review

pytestmark = pytest.mark.integration


def test_import_preserves_sources_and_never_revives_reviewed_tasks(clean_database, monkeypatch):
    monkeypatch.setattr("gcrm.tools.db_organizations.geocode", lambda city, country: None)
    organization = save_organization("Example GmbH", "Augsburg", source="test_fixture")
    deal = get_deals("organization", organization)[0]
    set_deal_next_step(deal["id"], "Send proposal", date(2026, 12, 1))
    note = log_meeting_note(organization, "phone", "Spoke", follow_up_text="Call again")

    import_legacy_follow_ups()
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id, source_kind, source_id, task_text, status FROM follow_ups ORDER BY source_kind")
        tasks = cursor.fetchall()
        assert [(task["source_kind"], task["source_id"], task["task_text"], task["status"]) for task in tasks] == [
            ("deal", deal["id"], "Send proposal", "review"),
            ("interaction", note, "Call again", "review"),
        ]
        cursor.execute("UPDATE follow_ups SET status='dismissed', dismissed_at=NOW() WHERE id=%s", (tasks[0]["id"],))

    import_legacy_follow_ups()
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT status FROM follow_ups ORDER BY source_kind")
        assert [task["status"] for task in cursor.fetchall()] == ["dismissed", "review"]


def test_new_activity_classification_is_saved_with_its_source(clean_database, monkeypatch):
    monkeypatch.setattr("gcrm.tools.db_organizations.geocode", lambda city, country: None)
    organization = save_organization("Example GmbH", "Augsburg", source="test_fixture")
    note = log_meeting_note(organization, "phone", "Spoke", follow_up_text="Send details",
                            follow_up_type="commitment")
    import_legacy_follow_ups()
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT task_text, task_type, status FROM follow_ups WHERE source_kind='interaction' "
                       "AND source_id=%s", (note,))
        assert [tuple(row.values()) for row in cursor.fetchall()] == [("Send details", "commitment", "active")]


def test_review_activates_only_with_a_valid_type_and_text(clean_database, monkeypatch):
    monkeypatch.setattr("gcrm.tools.db_organizations.geocode", lambda city, country: None)
    organization = save_organization("Example GmbH", "Augsburg", source="test_fixture")
    note = log_meeting_note(organization, "phone", "Spoke", follow_up_text="Send details")
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id, updated_at FROM follow_ups WHERE source_kind='interaction' AND source_id=%s", (note,))
        task = cursor.fetchone()
    with pytest.raises(ValueError):
        resolve_review(task["id"], "keep", task["updated_at"], task_type="", task_text="Send details")
    resolve_review(task["id"], "keep", task["updated_at"], task_type="commitment", task_text="Send details")
    import_legacy_follow_ups()
    assert [(row["id"], row["task_text"]) for row in list_follow_ups()] == [(task["id"], "Send details")]


def test_review_can_link_general_promise_to_its_own_deal(clean_database, monkeypatch):
    monkeypatch.setattr("gcrm.tools.db_organizations.geocode", lambda city, country: None)
    organization = save_organization("Example GmbH", "Augsburg", source="test_fixture")
    deal = get_deals("organization", organization)[0]
    note = log_meeting_note(organization, "phone", "Spoke", follow_up_text="Send details")
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id, updated_at FROM follow_ups WHERE source_kind='interaction' AND source_id=%s", (note,))
        task = cursor.fetchone()
    resolve_review(task["id"], "keep", task["updated_at"], task_type="commitment", task_text="Send details",
                   deal_id=deal["id"])
    assert list_follow_ups()[0]["deal_id"] == deal["id"]


def test_migration_snapshots_existing_sources_without_importing_generated_history(clean_database, monkeypatch):
    monkeypatch.setattr("gcrm.tools.db_organizations.geocode", lambda city, country: None)
    organization = save_organization("Example GmbH", "Augsburg", source="test_fixture")
    deal = get_deals("organization", organization)[0]
    migration = Path(__file__).parents[2] / "gcrm/db/migrations/099_follow_ups.sql"
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("DROP TABLE follow_ups")
        cursor.execute("UPDATE deals SET next_step='Send proposal', next_step_date='2026-12-01' WHERE id=%s",
                       (deal["id"],))
        cursor.execute("INSERT INTO interactions (contact_id, workspace_id, interaction_date, method, next_action) "
                       "SELECT id, workspace_id, '2026-11-01', 'phone', 'Call later' FROM contacts WHERE id=%s "
                       "RETURNING id", (organization,))
        interaction = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO interactions (contact_id, workspace_id, interaction_date, method, next_action) "
                       "SELECT id, workspace_id, '2026-11-01', 'next_step', 'Generated history' "
                       "FROM contacts WHERE id=%s", (organization,))
        cursor.execute(migration.read_text())
        cursor.execute("SELECT source_kind, source_id, task_text, status FROM follow_ups ORDER BY source_kind")
        assert [tuple(row.values()) for row in cursor.fetchall()] == [
            ("deal", deal["id"], "Send proposal", "review"), ("interaction", interaction, "Call later", "review")]
    import_legacy_follow_ups()
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT count(*) AS total FROM follow_ups")
        assert cursor.fetchone()["total"] == 2
