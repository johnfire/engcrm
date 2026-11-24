import psycopg2
import pytest

from gcrm.audit_context import audit_scope
from gcrm.db.connection import db
from gcrm.tools.people_merge import merge_people

pytestmark = pytest.mark.integration


def test_contact_changes_are_captured_without_values(clean_database, migrated_database):
    with psycopg2.connect(migrated_database) as connection, connection.cursor() as cursor:
        cursor.execute("INSERT INTO contacts(name) VALUES ('Sample business') RETURNING id, sync_id")
        contact_id, sync_id = cursor.fetchone()
        cursor.execute("UPDATE contacts SET phone='123' WHERE id=%s", (contact_id,))
        cursor.execute("UPDATE contacts SET updated_at=clock_timestamp() WHERE id=%s", (contact_id,))
        cursor.execute("UPDATE contacts SET deleted_at=clock_timestamp() WHERE id=%s", (contact_id,))
        cursor.execute(
            "SELECT entity_kind, entity_sync_id, operation FROM sync_entity_changes ORDER BY sequence"
        )
        assert cursor.fetchall() == [
            ("organization", sync_id, "upsert"),
            ("organization", sync_id, "upsert"),
            ("organization", sync_id, "soft_delete"),
        ]
        cursor.execute(
            "SELECT field_name FROM sync_field_versions WHERE entity_sync_id=%s AND field_name='phone'",
            (sync_id,),
        )
        assert cursor.fetchall() == [("phone",)]


def test_change_capture_preserves_actor_and_correlation(clean_database):
    with audit_scope("user:123", "user", "sync-test-request"), db() as connection:
        connection.cursor().execute("INSERT INTO contacts(name) VALUES ('Audit example')")
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT actor, correlation_id FROM sync_entity_changes")
        assert [tuple(row.values()) for row in cursor.fetchall()] == [("user:123", "sync-test-request")]


@pytest.mark.parametrize(("actor_type", "source"), [("user", "web"), ("ai", "agent"), ("mcp", "mcp")])
def test_field_clocks_record_writer_source(clean_database, actor_type, source):
    with audit_scope("test-actor", actor_type, "source-check"), db() as connection:
        cursor = connection.cursor()
        cursor.execute("INSERT INTO contacts(name) VALUES ('Source check') RETURNING sync_id")
        sync_id = cursor.fetchone()["sync_id"]
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT source FROM sync_field_versions WHERE entity_sync_id=%s AND field_name='name'", (sync_id,))
        assert cursor.fetchone()["source"] == source


def test_merge_records_redirect_for_removed_person(clean_database):
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("INSERT INTO people(name) VALUES ('Kept'), ('Removed') RETURNING id, sync_id")
        keep, removed = cursor.fetchall()
    merge_people(keep["id"], removed["id"], apply=True)
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT operation, merge_target_sync_id FROM sync_entity_changes "
            "WHERE entity_sync_id=%s ORDER BY sequence DESC LIMIT 1", (removed["sync_id"],)
        )
        change = cursor.fetchone()
        assert change["operation"] == "merge_redirect"
        assert str(change["merge_target_sync_id"]) == str(keep["sync_id"])


def test_cascade_erasure_emits_person_and_note_purge_markers(clean_database, migrated_database):
    with psycopg2.connect(migrated_database) as connection, connection.cursor() as cursor:
        cursor.execute("INSERT INTO people(name) VALUES ('Private') RETURNING id, sync_id")
        person_id, person_sync_id = cursor.fetchone()
        cursor.execute(
            "INSERT INTO people_interactions(person_id, note) VALUES (%s, 'Private note') RETURNING sync_id",
            (person_id,),
        )
        note_sync_id = cursor.fetchone()[0]
        cursor.execute("DELETE FROM people WHERE id=%s", (person_id,))
        cursor.execute(
            "SELECT entity_kind, entity_sync_id, operation FROM sync_entity_changes "
            "WHERE operation='hard_erase' ORDER BY entity_kind"
        )
        assert cursor.fetchall() == [
            ("person", person_sync_id, "hard_erase"),
            ("person_note", note_sync_id, "hard_erase"),
        ]
        cursor.execute("SELECT COUNT(*) FROM sync_field_versions WHERE entity_sync_id IN (%s, %s)",
                       (person_sync_id, note_sync_id))
        assert cursor.fetchone()[0] == 0


def test_hard_erasure_removes_previously_provisional_personal_values(clean_database, migrated_database):
    with psycopg2.connect(migrated_database) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT id FROM workspaces WHERE slug='default'")
        workspace_id = cursor.fetchone()[0]
        cursor.execute("INSERT INTO users(email,password_hash,workspace_id) VALUES "
                       "('sync-erase@example.test','hash',%s) RETURNING id", (workspace_id,))
        user_id = cursor.fetchone()[0]
        cursor.execute("INSERT INTO people(name) VALUES ('Private') RETURNING id, sync_id")
        person_id, person_sync_id = cursor.fetchone()
        cursor.execute(
            "INSERT INTO provisional_mobile_changes(workspace_id,user_id,device_id,mutation_id,"
            "entity_kind,entity_sync_id,reason,patch,changed_at,expires_at) "
            "VALUES (%s,%s,gen_random_uuid(),gen_random_uuid(),'person',%s,'soft_deleted',"
            "'{\"phone\":\"private\"}',now(),now()+interval '30 days')",
            (workspace_id, user_id, person_sync_id),
        )
        cursor.execute("DELETE FROM people WHERE id=%s", (person_id,))
        cursor.execute("SELECT COUNT(*) FROM provisional_mobile_changes WHERE entity_sync_id=%s", (person_sync_id,))
        assert cursor.fetchone()[0] == 0


def test_private_rating_change_targets_only_its_owner(clean_database, migrated_database):
    with psycopg2.connect(migrated_database) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT id FROM workspaces WHERE slug='default'")
        workspace_id = cursor.fetchone()[0]
        cursor.execute("INSERT INTO users(email,password_hash,workspace_id) VALUES "
                       "('sync-rating@example.test','hash',%s) RETURNING id", (workspace_id,))
        user_id = cursor.fetchone()[0]
        cursor.execute("INSERT INTO contacts(name) VALUES ('Rated') RETURNING id,sync_id")
        contact_id, sync_id = cursor.fetchone()
        cursor.execute("INSERT INTO contact_user_priorities(workspace_id,user_id,contact_id,priority) "
                       "VALUES (%s,%s,%s,1)", (workspace_id, user_id, contact_id))
        cursor.execute("SELECT entity_sync_id,target_user_id FROM sync_entity_changes "
                       "WHERE target_user_id IS NOT NULL")
        assert cursor.fetchall() == [(sync_id, user_id)]
