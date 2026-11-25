from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from gcrm.audit_context import audit_scope
from gcrm.db.connection import db
from gcrm.sync.contracts import SyncUpdate
from gcrm.tools.db_sync_push import apply_sync_update
from gcrm.tools.people_merge import merge_people
from gcrm.workspace_context import workspace_scope

pytestmark = pytest.mark.integration


def test_offline_updates_use_save_time_and_retries_are_idempotent(clean_database):
    device_id = uuid4()
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug='default'")
        workspace_id = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO users(email,password_hash,workspace_id) VALUES "
                       "('push-test@example.test','hash',%s) RETURNING id", (workspace_id,))
        user_id = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO mobile_sync_devices(workspace_id,user_id,device_id,server_environment,app_version,schema_version) "
                       "VALUES (%s,%s,%s,'production','1',1)", (workspace_id, user_id, str(device_id)))
        cursor.execute("INSERT INTO contacts(name,phone) VALUES ('Initial','111') RETURNING sync_id")
        sync_id = cursor.fetchone()["sync_id"]
    now = datetime.now(UTC)
    old = SyncUpdate(mutation_id=uuid4(), device_id=device_id, entity_kind="organization", entity_sync_id=sync_id,
                     operation="update", changed_at=now-timedelta(hours=1), patch={"phone": "old phone"})
    newer = SyncUpdate(mutation_id=uuid4(), device_id=device_id, entity_kind="organization", entity_sync_id=sync_id,
                       operation="update", changed_at=now+timedelta(minutes=1), patch={"phone": "new phone"})
    with workspace_scope(workspace_id), audit_scope(f"user:{user_id}", "user", "push-test"):
        assert apply_sync_update(workspace_id, user_id, "production", old)["status"] == "ignored_older"
        first = apply_sync_update(workspace_id, user_id, "production", newer)
        assert first["status"] == "applied"
        assert apply_sync_update(workspace_id, user_id, "production", newer)["status"] == "applied"
        changed_retry = newer.model_copy(update={"patch": {"phone": "different"}})
        with pytest.raises(ValueError, match="mutation ID"):
            apply_sync_update(workspace_id, user_id, "production", changed_retry)
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT phone FROM contacts WHERE sync_id=%s", (sync_id,))
        assert cursor.fetchone()["phone"] == "new phone"
        cursor.execute("SELECT count(*) AS n FROM sync_mutations WHERE mutation_id=%s", (str(newer.mutation_id),))
        assert cursor.fetchone()["n"] == 1
        cursor.execute("SELECT changed_at,device_id,mutation_id FROM sync_field_versions WHERE entity_sync_id=%s AND field_name='phone'", (sync_id,))
        clock = cursor.fetchone()
        assert clock["changed_at"] == newer.changed_at
        assert str(clock["device_id"]) == str(device_id)
        assert str(clock["mutation_id"]) == str(newer.mutation_id)


def test_noop_save_advances_the_field_clock_and_protects_against_an_older_edit(clean_database):
    device_id = uuid4()
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug='default'")
        workspace = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO users(email,password_hash,workspace_id) VALUES "
                       "('push-noop@example.test','hash',%s) RETURNING id", (workspace,))
        user_id = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO mobile_sync_devices(workspace_id,user_id,device_id,server_environment,app_version,schema_version) "
                       "VALUES (%s,%s,%s,'production','1',1)", (workspace, user_id, str(device_id)))
        cursor.execute("INSERT INTO contacts(name,phone) VALUES ('Company','123') RETURNING sync_id")
        sync_id = cursor.fetchone()["sync_id"]
    now = datetime.now(UTC)
    noop = SyncUpdate(mutation_id=uuid4(), device_id=device_id, entity_kind="organization", entity_sync_id=sync_id,
                      operation="update", changed_at=now+timedelta(minutes=2), patch={"phone": "123"})
    older = SyncUpdate(mutation_id=uuid4(), device_id=device_id, entity_kind="organization", entity_sync_id=sync_id,
                       operation="update", changed_at=now+timedelta(minutes=1), patch={"phone": "wrong"})
    with workspace_scope(workspace), audit_scope(f"user:{user_id}", "user", "push-noop"):
        assert apply_sync_update(workspace, user_id, "production", noop)["status"] == "applied"
        assert apply_sync_update(workspace, user_id, "production", older)["status"] == "ignored_older"
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT phone FROM contacts WHERE sync_id=%s", (sync_id,))
        assert cursor.fetchone()["phone"] == "123"


def test_future_clock_is_rejected_without_changing_the_record(clean_database):
    device_id = uuid4()
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug='default'")
        workspace = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO users(email,password_hash,workspace_id) VALUES "
                       "('push-clock@example.test','hash',%s) RETURNING id", (workspace,))
        user_id = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO mobile_sync_devices(workspace_id,user_id,device_id,server_environment,app_version,schema_version) "
                       "VALUES (%s,%s,%s,'production','1',1)", (workspace, user_id, str(device_id)))
        cursor.execute("INSERT INTO contacts(name,phone) VALUES ('Company','123') RETURNING sync_id")
        sync_id = cursor.fetchone()["sync_id"]
    future = SyncUpdate(mutation_id=uuid4(), device_id=device_id, entity_kind="organization", entity_sync_id=sync_id,
                        operation="update", changed_at=datetime.now(UTC)+timedelta(minutes=6), patch={"phone": "456"})
    with workspace_scope(workspace), audit_scope(f"user:{user_id}", "user", "push-clock"):
        assert apply_sync_update(workspace, user_id, "production", future)["status"] == "rejected_clock"
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT phone FROM contacts WHERE sync_id=%s", (sync_id,))
        assert cursor.fetchone()["phone"] == "123"


def test_offline_deal_next_step_updates_the_follow_up_worklist(clean_database):
    device_id = uuid4()
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug='default'")
        workspace = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO users(email,password_hash,workspace_id) VALUES "
                       "('push-followup@example.test','hash',%s) RETURNING id", (workspace,))
        user_id = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO mobile_sync_devices(workspace_id,user_id,device_id,server_environment,app_version,schema_version) "
                       "VALUES (%s,%s,%s,'production','1',1)", (workspace, user_id, str(device_id)))
        cursor.execute("INSERT INTO contacts(name) VALUES ('Company') RETURNING id")
        contact_id = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO deals(workspace_id,offer_id,contact_id) "
                       "VALUES (%s,offer_id_for(%s,'consulting'),%s) RETURNING id,sync_id", (workspace, workspace, contact_id))
        deal = cursor.fetchone()
    update = SyncUpdate(mutation_id=uuid4(), device_id=device_id, entity_kind="deal", entity_sync_id=deal["sync_id"],
                        operation="update", changed_at=datetime.now(UTC)+timedelta(minutes=1),
                        patch={"next_step": "Send proposal", "next_step_date": "2026-12-01"})
    with workspace_scope(workspace), audit_scope(f"user:{user_id}", "user", "push-followup"):
        assert apply_sync_update(workspace, user_id, "production", update)["status"] == "applied"
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT task_text,due_date,status FROM follow_ups WHERE deal_id=%s", (deal["id"],))
        task = cursor.fetchone()
        assert task["task_text"] == "Send proposal"
        assert task["due_date"].isoformat() == "2026-12-01"
        assert task["status"] == "review"


def test_erased_merge_survivor_never_accepts_a_provisional_patch(clean_database):
    device_id = uuid4()
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug='default'")
        workspace = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO users(email,password_hash,workspace_id) VALUES "
                       "('push-erase@example.test','hash',%s) RETURNING id", (workspace,))
        user_id = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO mobile_sync_devices(workspace_id,user_id,device_id,server_environment,app_version,schema_version) "
                       "VALUES (%s,%s,%s,'production','1',1)", (workspace, user_id, str(device_id)))
        cursor.execute("INSERT INTO people(name) VALUES ('Kept'),('Duplicate') RETURNING id,sync_id")
        keep, duplicate = cursor.fetchall()
    merge_people(keep["id"], duplicate["id"], apply=True)
    with db() as connection:
        connection.cursor().execute("DELETE FROM people WHERE id=%s", (keep["id"],))
    update = SyncUpdate(mutation_id=uuid4(), device_id=device_id, entity_kind="person", entity_sync_id=duplicate["sync_id"],
                        operation="update", changed_at=datetime.now(UTC), patch={"phone": "private"})
    with workspace_scope(workspace), audit_scope(f"user:{user_id}", "user", "push-erase"):
        result = apply_sync_update(workspace, user_id, "production", update)
    assert result["status"] == "erased"
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT count(*) AS n FROM provisional_mobile_changes")
        assert cursor.fetchone()["n"] == 0


def test_erasing_a_soft_deleted_target_purges_its_proposal_and_notifies_a_retry(clean_database):
    device_id = uuid4()
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug='default'")
        workspace = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO users(email,password_hash,workspace_id) VALUES "
                       "('push-soft@example.test','hash',%s) RETURNING id", (workspace,))
        user_id = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO mobile_sync_devices(workspace_id,user_id,device_id,server_environment,app_version,schema_version) "
                       "VALUES (%s,%s,%s,'production','1',1)", (workspace, user_id, str(device_id)))
        cursor.execute("INSERT INTO people(name,deleted_at) VALUES ('Deleted',now()) RETURNING id,sync_id")
        person = cursor.fetchone()
    update = SyncUpdate(mutation_id=uuid4(), device_id=device_id, entity_kind="person", entity_sync_id=person["sync_id"],
                        operation="update", changed_at=datetime.now(UTC), patch={"phone": "private"})
    with workspace_scope(workspace), audit_scope(f"user:{user_id}", "user", "push-soft"):
        assert apply_sync_update(workspace, user_id, "production", update)["status"] == "provisional"
        with db() as connection:
            connection.cursor().execute("DELETE FROM people WHERE id=%s", (person["id"],))
        assert apply_sync_update(workspace, user_id, "production", update)["status"] == "erased"
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT count(*) AS n FROM provisional_mobile_changes")
        assert cursor.fetchone()["n"] == 0


def test_retry_after_applied_record_is_erased_reports_erasure(clean_database):
    device_id = uuid4()
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug='default'")
        workspace = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO users(email,password_hash,workspace_id) VALUES "
                       "('push-retry-erased@example.test','hash',%s) RETURNING id", (workspace,))
        user_id = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO mobile_sync_devices(workspace_id,user_id,device_id,server_environment,app_version,schema_version) "
                       "VALUES (%s,%s,%s,'production','1',1)", (workspace, user_id, str(device_id)))
        cursor.execute("INSERT INTO people(name) VALUES ('Person') RETURNING id,sync_id")
        person = cursor.fetchone()
    update = SyncUpdate(mutation_id=uuid4(), device_id=device_id, entity_kind="person", entity_sync_id=person["sync_id"],
                        operation="update", changed_at=datetime.now(UTC)+timedelta(minutes=1), patch={"phone": "123"})
    with workspace_scope(workspace), audit_scope(f"user:{user_id}", "user", "push-retry-erased"):
        assert apply_sync_update(workspace, user_id, "production", update)["status"] == "applied"
        with db() as connection:
            connection.cursor().execute("DELETE FROM people WHERE id=%s", (person["id"],))
        assert apply_sync_update(workspace, user_id, "production", update)["status"] == "erased"


def test_retry_after_applied_record_is_soft_deleted_includes_marker(clean_database):
    device_id = uuid4()
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug='default'")
        workspace = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO users(email,password_hash,workspace_id) VALUES "
                       "('push-retry-deleted@example.test','hash',%s) RETURNING id", (workspace,))
        user_id = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO mobile_sync_devices(workspace_id,user_id,device_id,server_environment,app_version,schema_version) "
                       "VALUES (%s,%s,%s,'production','1',1)", (workspace, user_id, str(device_id)))
        cursor.execute("INSERT INTO people(name) VALUES ('Person') RETURNING id,sync_id")
        person = cursor.fetchone()
    update = SyncUpdate(mutation_id=uuid4(), device_id=device_id, entity_kind="person", entity_sync_id=person["sync_id"],
                        operation="update", changed_at=datetime.now(UTC)+timedelta(minutes=1), patch={"phone": "123"})
    with workspace_scope(workspace), audit_scope(f"user:{user_id}", "user", "push-retry-deleted"):
        assert apply_sync_update(workspace, user_id, "production", update)["status"] == "applied"
        with db() as connection:
            connection.cursor().execute("UPDATE people SET deleted_at=now() WHERE id=%s", (person["id"],))
        replay = apply_sync_update(workspace, user_id, "production", update)
        assert replay["status"] == "applied"
        assert replay["entity"] is None
        assert replay["target_state"]["operation"] == "soft_delete"
