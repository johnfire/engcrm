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
