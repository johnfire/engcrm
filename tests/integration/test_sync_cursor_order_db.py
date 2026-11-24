from concurrent.futures import ThreadPoolExecutor
from threading import Event

import psycopg2
import pytest

pytestmark = pytest.mark.integration


def insert_change(connection, workspace_id):
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO sync_entity_changes(workspace_id, entity_kind, entity_sync_id, operation) "
            "VALUES (%s, 'person', gen_random_uuid(), 'upsert') RETURNING sequence",
            (workspace_id,),
        )
        return cursor.fetchone()[0]


def test_cursor_cannot_pass_an_uncommitted_change(clean_database, migrated_database):
    with psycopg2.connect(migrated_database) as first, psycopg2.connect(migrated_database) as second:
        with first.cursor() as cursor:
            cursor.execute("SELECT id FROM workspaces WHERE slug = 'default'")
            workspace_id = cursor.fetchone()[0]
        first_sequence = insert_change(first, workspace_id)
        started = Event()

        def commit_second_change():
            started.set()
            sequence = insert_change(second, workspace_id)
            second.commit()
            return sequence

        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(commit_second_change)
            assert started.wait(2)
            try:
                with pytest.raises(TimeoutError):
                    pending.result(timeout=0.25)
            finally:
                first.commit()
            assert pending.result(timeout=5) > first_sequence


def test_cursor_high_water_survives_deletion_of_a_users_private_events(clean_database, migrated_database):
    with psycopg2.connect(migrated_database) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT id FROM workspaces WHERE slug='default'")
        workspace = cursor.fetchone()[0]
        cursor.execute("INSERT INTO users(email,password_hash,workspace_id) "
                       "VALUES ('cursor-user@example.test','hash',%s) RETURNING id", (workspace,))
        user_id = cursor.fetchone()[0]
        cursor.execute("INSERT INTO contacts(name) VALUES ('Rated') RETURNING id")
        contact_id = cursor.fetchone()[0]
        cursor.execute("INSERT INTO contact_user_priorities(workspace_id,user_id,contact_id,priority) "
                       "VALUES (%s,%s,%s,1)", (workspace, user_id, contact_id))
        cursor.execute("SELECT max(sequence) FROM sync_entity_changes WHERE workspace_id=%s", (workspace,))
        high_water = cursor.fetchone()[0]
        cursor.execute("DELETE FROM users WHERE id=%s", (user_id,))
        cursor.execute("SELECT last_sequence FROM sync_workspace_cursors WHERE workspace_id=%s", (workspace,))
        assert cursor.fetchone()[0] == high_water
