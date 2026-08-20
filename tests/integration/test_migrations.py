"""Real-PostgreSQL migration and repository integration coverage."""
import sys
from pathlib import Path
from subprocess import run

import pytest

from gcrm.db.connection import db
from gcrm.tools.db import get_contacts_ready_for_outreach, save_contact
from gcrm.tools.db_agent_runs import finish_run, start_run
from gcrm.tools.db_personal_priorities import (
    get_personal_priority,
    set_personal_priority,
)
from gcrm.tools.privacy_retention import purge_expired_data

pytestmark = pytest.mark.integration


def test_all_migrations_apply_and_are_idempotent(migrated_database):
    """Every migration applies to an empty service database and reruns safely."""
    repository_root = Path(__file__).parents[2]
    run([sys.executable, "scripts/migrate.py"], cwd=repository_root, check=True)

    migration_files = list((repository_root / "gcrm" / "db" / "migrations").glob("*.sql"))
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT migration_name FROM schema_migrations")
        applied_migrations = {row["migration_name"] for row in cursor.fetchall()}

    assert {migration.name for migration in migration_files} <= applied_migrations


def test_contact_repository_persists_and_hides_soft_deleted_records(clean_database):
    """Repository queries operate against the migrated PostgreSQL schema."""
    contact_id = save_contact(
        "Integration Cafe",
        "Munich",
        type="cafe",
        email="integration@example.test",
        pipeline_stage="suspect",
        status="ready",
    )

    assert [contact["id"] for contact in get_contacts_ready_for_outreach()] == [contact_id]

    with db() as connection:
        connection.cursor().execute("UPDATE contacts SET deleted_at = NOW() WHERE id = %s", (contact_id,))

    assert get_contacts_ready_for_outreach() == []


def test_agent_run_events_record_the_ai_actor_and_correlation_id(clean_database):
    """AI work is attributable even when it originates outside an HTTP request."""
    run_id = start_run("scout_agent", {"limit": 1})
    finish_run(run_id, "completed", "scored one contact", {})

    with db() as connection:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT actor, actor_type, correlation_id FROM audit_log "
            "WHERE action = 'agent.run_finished' AND target = %s",
            (f"agent_run:{run_id}",),
        )
        audit_event = cursor.fetchone()

    assert dict(audit_event) == {
        "actor": "agent:scout_agent",
        "actor_type": "ai",
        "correlation_id": f"run:{run_id}",
    }


def test_personal_priorities_are_private_per_user(clean_database):
    """Two users can independently rate one contact in their workspace."""
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug = 'default'")
        workspace_id = cursor.fetchone()["id"]
        cursor.execute(
            """
            INSERT INTO users (email, password_hash, role, workspace_id)
            VALUES
                ('priority-one@example.test', 'hash', 'spectator', %s),
                ('priority-two@example.test', 'hash', 'spectator', %s)
            RETURNING id
            """,
            (workspace_id, workspace_id),
        )
        user_ids = [row["id"] for row in cursor.fetchall()]
        cursor.execute(
            """
            INSERT INTO contacts (name, status, workspace_id)
            VALUES ('Priority Venue', 'cold', %s)
            RETURNING id
            """,
            (workspace_id,),
        )
        contact_id = cursor.fetchone()["id"]

    assert set_personal_priority(user_ids[0], workspace_id, contact_id, 1) == (True, 1)
    assert set_personal_priority(user_ids[1], workspace_id, contact_id, 5) == (True, 5)
    assert get_personal_priority(user_ids[0], workspace_id, contact_id) == 1
    assert get_personal_priority(user_ids[1], workspace_id, contact_id) == 5

    assert set_personal_priority(user_ids[0], workspace_id, contact_id, None) == (True, None)
    assert get_personal_priority(user_ids[0], workspace_id, contact_id) is None
    assert get_personal_priority(user_ids[1], workspace_id, contact_id) == 5

    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("DELETE FROM users WHERE id = %s", (user_ids[1],))
        cursor.execute(
            "SELECT count(*) AS count FROM contact_user_priorities",
        )
        assert cursor.fetchone()["count"] == 0

    assert set_personal_priority(user_ids[0], workspace_id, contact_id, 2) == (True, 2)
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("DELETE FROM contacts WHERE id = %s", (contact_id,))
        cursor.execute(
            "SELECT count(*) AS count FROM contact_user_priorities",
        )
        assert cursor.fetchone()["count"] == 0


def test_retention_erases_a_contact_and_all_linked_records_at_three_years(clean_database):
    """A contact expires from creation time with its contact-linked data."""
    contact_id = save_contact("Expired Cafe", "Munich", type="cafe", status="cold")

    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("UPDATE contacts SET created_at = NOW() - INTERVAL '3 years 1 day' WHERE id = %s", (contact_id,))
        cursor.execute("INSERT INTO interactions (contact_id, interaction_date) VALUES (%s, CURRENT_DATE)", (contact_id,))
        cursor.execute("INSERT INTO ai_analysis (contact_id, raw_response) VALUES (%s, 'contact-specific output')", (contact_id,))
        cursor.execute("INSERT INTO approval_queue (contact_id, draft_subject, draft_body) VALUES (%s, 'Subject', 'Draft')", (contact_id,))
        cursor.execute("INSERT INTO inbox_messages (message_id, from_email, matched_contact_id) VALUES ('expired-contact', 'expired@example.test', %s)", (contact_id,))
        cursor.execute("INSERT INTO people (name, contact_id) VALUES ('Expired Person', %s)", (contact_id,))
        cursor.execute("INSERT INTO outreach_outcomes (contact_id) VALUES (%s)", (contact_id,))

    counts = purge_expired_data()

    assert counts["contacts"] == 1
    with db() as connection:
        cursor = connection.cursor()
        for table_name in ("contacts", "interactions", "ai_analysis", "approval_queue", "inbox_messages", "people", "outreach_outcomes"):
            cursor.execute(f"SELECT count(*) AS count FROM {table_name}")
            assert cursor.fetchone()["count"] == 0
