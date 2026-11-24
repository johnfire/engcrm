from pathlib import Path

import psycopg2
import pytest

pytestmark = pytest.mark.integration


def test_existing_records_receive_baseline_field_clocks(clean_database, migrated_database):
    migration = Path(__file__).parents[2] / "gcrm/db/migrations/105_sync_field_backfill.sql"
    with psycopg2.connect(migrated_database) as connection, connection.cursor() as cursor:
        cursor.execute("INSERT INTO contacts(name,phone) VALUES ('Existing company','123') RETURNING sync_id")
        sync_id = cursor.fetchone()[0]
        cursor.execute("DELETE FROM sync_field_versions WHERE entity_sync_id=%s", (sync_id,))
        cursor.execute(migration.read_text())
        cursor.execute("SELECT field_name,source FROM sync_field_versions WHERE entity_sync_id=%s "
                       "AND field_name IN ('name','phone') ORDER BY field_name", (sync_id,))
        assert cursor.fetchall() == [("name", "migration"), ("phone", "migration")]
