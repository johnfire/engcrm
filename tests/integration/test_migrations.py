"""Real-PostgreSQL migration and repository integration coverage."""
import sys
from pathlib import Path
from subprocess import run

import pytest

from gcrm.db.connection import db
from gcrm.tools.db import get_cold_contacts, save_contact
from gcrm.tools.db_agent_runs import finish_run, start_run

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
        status="cold",
    )

    assert [contact["id"] for contact in get_cold_contacts()] == [contact_id]

    with db() as connection:
        connection.cursor().execute("UPDATE contacts SET deleted_at = NOW() WHERE id = %s", (contact_id,))

    assert get_cold_contacts() == []


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
