"""The PostgreSQL role protects even queries that omit a workspace predicate."""
from contextlib import contextmanager

import psycopg2
import pytest

from gcrm.db.connection import db
from gcrm.supervisor.job_environment import job_environment
from gcrm.workspace_context import set_workspace_id

pytestmark = [pytest.mark.integration, pytest.mark.security_boundary]


@contextmanager
def workspace_scope(workspace_id):
    set_workspace_id(workspace_id)
    try:
        yield
    finally:
        set_workspace_id(None)


@pytest.fixture
def two_workspaces(clean_database):
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug='default'")
        local = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO workspaces(name,slug) VALUES ('Security other','security-other') "
                       "ON CONFLICT(slug) DO UPDATE SET name=EXCLUDED.name RETURNING id")
        foreign = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO contacts(name,workspace_id) VALUES ('Local',%s),('Foreign',%s) RETURNING id", (local, foreign))
        contacts = [row["id"] for row in cursor.fetchall()]
    return local, foreign, contacts


def test_role_cannot_bypass_rls_and_unfiltered_reads_only_return_own_records(two_workspaces):
    local, foreign, contacts = two_workspaces
    for workspace, contact in zip((local, foreign), contacts, strict=True):
        with workspace_scope(workspace), db() as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT current_user AS role")
            assert cursor.fetchone()["role"] == "engcrm_workspace"
            cursor.execute("SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user")
            assert dict(cursor.fetchone()) == {"rolsuper": False, "rolbypassrls": False}
            cursor.execute("SELECT id FROM contacts")
            assert [row["id"] for row in cursor.fetchall()] == [contact]


def test_related_rows_follow_their_parent_and_foreign_parent_writes_are_refused(two_workspaces):
    local, foreign, contacts = two_workspaces
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("INSERT INTO people(name,contact_id,workspace_id) VALUES ('Other person',%s,%s) RETURNING id", (contacts[1], foreign))
        person = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO people_interactions(person_id,note) VALUES (%s,'Private')", (person,))
    with workspace_scope(local), db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT note FROM people_interactions")
        assert cursor.fetchall() == []
    with workspace_scope(local), pytest.raises(psycopg2.errors.InsufficientPrivilege), db() as connection:
        connection.cursor().execute("INSERT INTO people(name,contact_id) VALUES ('Local with foreign parent',%s)", (contacts[1],))


def test_every_workspace_column_has_a_policy_and_new_rows_get_the_active_workspace(two_workspaces):
    local, foreign, _ = two_workspaces
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT c.table_name FROM information_schema.columns c JOIN pg_tables t ON t.tablename=c.table_name "
                       "AND t.schemaname=c.table_schema WHERE c.table_schema='public' AND c.column_name='workspace_id' AND NOT t.rowsecurity")
        assert cursor.fetchall() == []
    with workspace_scope(foreign), db() as connection:
        cursor = connection.cursor()
        cursor.execute("INSERT INTO contacts(name) VALUES ('New foreign') RETURNING workspace_id")
        assert cursor.fetchone()["workspace_id"] == foreign
    with workspace_scope(local), db() as connection:
        cursor = connection.cursor()
        cursor.execute("UPDATE contacts SET name='Changed' WHERE name='New foreign'")
        assert cursor.rowcount == 0


def test_detached_job_receives_the_verified_workspace(two_workspaces):
    import os
    import subprocess
    import sys

    _, foreign, contacts = two_workspaces
    with workspace_scope(foreign):
        environment = job_environment()
    assert environment["GCRM_JOB_WORKSPACE_ID"] == str(foreign)
    # The fresh interpreter must apply the same role, not inherit operator access.
    command = "from gcrm.db.connection import db\nwith db() as c:\n cur=c.cursor();cur.execute('SELECT id FROM contacts');print([r['id'] for r in cur.fetchall()])"
    environment["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
    completed = subprocess.run([sys.executable, "-c", command], env=environment, text=True, capture_output=True, check=True)
    assert completed.stdout.strip() == str([contacts[1]])
