"""Reviewed profile persistence, original source preservation, and isolation."""
import pytest

from gcrm.audit_context import audit_scope
from gcrm.db.connection import db
from gcrm.tools.db_capture_linkedin import save_capture_profile
from gcrm.tools.db_people import save_person
from gcrm.workspace_context import set_workspace_id

pytestmark = pytest.mark.integration
PROFILE = "https://www.linkedin.com/in/anna-roth"


def test_profile_enriches_rescan_without_changing_origin_or_connection(clean_database):
    person_id = save_person("Anna Roth", source="manual")
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT created_at FROM people WHERE id=%s", (person_id,))
        created_at = cursor.fetchone()["created_at"]
    with audit_scope("user:42", "user", "profile-confirmation"):
        save_capture_profile(person_id, "https://de.linkedin.com/in/Anna-Roth?trk=scan")
        save_capture_profile(person_id, PROFILE)
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT source, created_at, linkedin_url, is_linkedin_contact FROM people WHERE id=%s", (person_id,))
        assert dict(cursor.fetchone()) == {"source": "manual", "created_at": created_at, "linkedin_url": PROFILE, "is_linkedin_contact": False}
        cursor.execute("SELECT actor, actor_type, correlation_id FROM audit_log WHERE action='person.linkedin_saved'")
        assert all(dict(entry) == {"actor": "user:42", "actor_type": "user", "correlation_id": "profile-confirmation"} for entry in cursor.fetchall())


def test_conflicting_profile_is_preserved(clean_database):
    person_id = save_person("Anna Roth", source="test_fixture")
    save_capture_profile(person_id, PROFILE)
    with pytest.raises(ValueError, match="different LinkedIn profile"):
        save_capture_profile(person_id, "https://linkedin.com/in/another-anna")
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT linkedin_url FROM people WHERE id=%s", (person_id,))
        assert cursor.fetchone()["linkedin_url"] == PROFILE


def test_profile_cannot_update_person_in_another_workspace(clean_database):
    person_id = save_person("Anna Roth", source="test_fixture")
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("INSERT INTO workspaces (name, slug) VALUES ('Lookup test', 'lookup-test') ON CONFLICT (slug) DO UPDATE SET name=EXCLUDED.name RETURNING id")
        other_workspace = cursor.fetchone()["id"]
    try:
        set_workspace_id(other_workspace)
        with pytest.raises(ValueError):
            save_capture_profile(person_id, PROFILE)
    finally:
        set_workspace_id(None)
