import psycopg2
import pytest


@pytest.mark.integration
def test_sync_entities_have_unique_non_null_uuid_identities(migrated_database):
    with psycopg2.connect(migrated_database) as connection, connection.cursor() as cursor:
        for table in ("contacts", "people", "deals", "interactions", "people_interactions"):
            cursor.execute(
                """
                SELECT data_type, is_nullable, column_default
                  FROM information_schema.columns
                 WHERE table_schema = 'public' AND table_name = %s AND column_name = 'sync_id'
                """,
                (table,),
            )
            column = cursor.fetchone()
            assert column is not None, table
            assert column[0:2] == ("uuid", "NO"), table
            assert "gen_random_uuid" in column[2], table
            cursor.execute(
                """
                SELECT EXISTS (
                    SELECT 1 FROM pg_index idx
                    JOIN pg_class tbl ON tbl.oid = idx.indrelid
                    JOIN pg_attribute attr ON attr.attrelid = tbl.oid AND attr.attnum = ANY(idx.indkey)
                    WHERE tbl.relname = %s AND idx.indisunique AND idx.indnkeyatts = 1
                      AND attr.attname = 'sync_id'
                )
                """,
                (table,),
            )
            assert cursor.fetchone()[0], table
