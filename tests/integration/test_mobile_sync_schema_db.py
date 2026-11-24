import psycopg2
import pytest

pytestmark = pytest.mark.integration


def test_sync_metadata_tables_enforce_workspace_isolation(migrated_database):
    with psycopg2.connect(migrated_database) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT tablename, rowsecurity, forcerowsecurity
              FROM pg_tables JOIN pg_class ON pg_class.relname = pg_tables.tablename
              CROSS JOIN LATERAL (SELECT pg_class.relforcerowsecurity AS forcerowsecurity) force
             WHERE schemaname = 'public' AND tablename IN
                   ('mobile_sync_devices', 'sync_entity_changes', 'sync_field_versions',
                    'sync_mutations', 'provisional_mobile_changes')
            """
        )
        tables = {name: (enabled, forced) for name, enabled, forced in cursor.fetchall()}
        assert len(tables) == 5
        assert all(state == (True, True) for state in tables.values())


def test_workspace_role_cannot_read_other_workspace_sync_metadata(clean_database, migrated_database):
    with psycopg2.connect(migrated_database) as connection, connection.cursor() as cursor:
        cursor.execute("INSERT INTO workspaces(name, slug) VALUES ('Sync other', 'sync-other') "
                       "ON CONFLICT(slug) DO UPDATE SET name=EXCLUDED.name RETURNING id")
        other_workspace = cursor.fetchone()[0]
        cursor.execute("SELECT id FROM workspaces WHERE slug = 'default'")
        local_workspace = cursor.fetchone()[0]
        cursor.execute(
            "INSERT INTO sync_entity_changes(workspace_id, entity_kind, entity_sync_id, operation) "
            "VALUES (%s, 'person', gen_random_uuid(), 'upsert'), "
            "(%s, 'person', gen_random_uuid(), 'upsert')", (local_workspace, other_workspace)
        )
        cursor.execute("SET LOCAL ROLE engcrm_workspace")
        cursor.execute("SELECT set_config('app.workspace_id', %s, true)", (str(local_workspace),))
        cursor.execute("SELECT workspace_id FROM sync_entity_changes")
        assert cursor.fetchall() == [(local_workspace,)]
        with pytest.raises(psycopg2.errors.InsufficientPrivilege):
            cursor.execute(
                "INSERT INTO sync_entity_changes(workspace_id, entity_kind, entity_sync_id, operation) "
                "VALUES (%s, 'person', gen_random_uuid(), 'upsert')", (other_workspace,)
            )


def test_device_cannot_be_assigned_to_a_user_in_another_workspace(clean_database, migrated_database):
    with psycopg2.connect(migrated_database) as connection, connection.cursor() as cursor:
        cursor.execute("INSERT INTO workspaces(name, slug) VALUES ('Sync other', 'sync-other') "
                       "ON CONFLICT(slug) DO UPDATE SET name=EXCLUDED.name RETURNING id")
        other_workspace = cursor.fetchone()[0]
        cursor.execute("SELECT id FROM workspaces WHERE slug = 'default'")
        local_workspace = cursor.fetchone()[0]
        cursor.execute(
            "INSERT INTO users(email, password_hash, workspace_id) VALUES (%s, %s, %s) RETURNING id",
            ("sync-other@example.test", "test", other_workspace),
        )
        other_user = cursor.fetchone()[0]
        cursor.execute("SET LOCAL ROLE engcrm_workspace")
        cursor.execute("SELECT set_config('app.workspace_id', %s, true)", (str(local_workspace),))
        with pytest.raises(psycopg2.errors.InsufficientPrivilege):
            cursor.execute(
                "INSERT INTO mobile_sync_devices(workspace_id, user_id, device_id, "
                "server_environment, app_version, schema_version) "
                "VALUES (%s, %s, gen_random_uuid(), 'test', '1', 1)",
                (local_workspace, other_user),
            )
