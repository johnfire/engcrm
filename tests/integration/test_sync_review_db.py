from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from psycopg2.extras import Json

from gcrm.audit_context import audit_scope
from gcrm.db.connection import db
from gcrm.sync.contracts import SyncUpdate
from gcrm.tools.db_sync_push import apply_sync_update
from gcrm.tools.db_sync_review import (
    apply_merged_provisional_change,
    discard_provisional_change,
    list_provisional_changes,
    read_review_outcomes,
    restore_provisional_change,
)
from gcrm.tools.people_merge import merge_people
from gcrm.workspace_context import workspace_scope

pytestmark = pytest.mark.integration


def test_review_queue_discard_is_audited_and_idempotent(clean_database):
    device_id, mutation_id, entity_id = uuid4(), uuid4(), uuid4()
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug='default'")
        workspace = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO users(email,password_hash,workspace_id) VALUES "
                       "('review-sync@example.test','hash',%s) RETURNING id", (workspace,))
        user = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO provisional_mobile_changes(workspace_id,user_id,device_id,mutation_id,entity_kind,"
                       "entity_sync_id,reason,patch,changed_at,expires_at) VALUES "
                       "(%s,%s,%s,%s,'person',%s,'soft_deleted',%s,now(),now()+interval '30 days') RETURNING id",
                       (workspace, user, str(device_id), str(mutation_id), str(entity_id), Json({"phone": "123"})))
        proposal = cursor.fetchone()["id"]
    with workspace_scope(workspace), audit_scope(f"user:{user}", "user", "review-test"):
        assert list_provisional_changes(workspace, user)[0]["patch"] == {"phone": "123"}
        assert discard_provisional_change(workspace, user, proposal) is True
        assert discard_provisional_change(workspace, user, proposal) is False
        assert list_provisional_changes(workspace, user) == []
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT status,patch,reviewed_by FROM provisional_mobile_changes WHERE id=%s", (proposal,))
        assert dict(cursor.fetchone()) == {"status": "discarded", "patch": None, "reviewed_by": user}
        cursor.execute("SELECT count(*) AS n FROM audit_log WHERE action='sync.review_discard' AND target=%s", (f"offline-change:{proposal}",))
        assert cursor.fetchone()["n"] == 1


def test_spectator_cannot_discard_an_offline_change(clean_database):
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug='default'")
        workspace = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO users(email,password_hash,workspace_id,role) VALUES "
                       "('spectator-sync@example.test','hash',%s,'spectator') RETURNING id", (workspace,))
        spectator = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO provisional_mobile_changes(workspace_id,user_id,device_id,mutation_id,entity_kind,"
                       "entity_sync_id,reason,patch,changed_at,expires_at) VALUES "
                       "(%s,%s,%s,%s,'person',%s,'soft_deleted',%s,now(),now()+interval '30 days') RETURNING id",
                       (workspace, spectator, str(uuid4()), str(uuid4()), str(uuid4()), Json({"phone": "123"})))
        proposal = cursor.fetchone()["id"]
    with workspace_scope(workspace), audit_scope(f"user:{spectator}", "user", "review-forbidden"):
        with pytest.raises(PermissionError):
            discard_provisional_change(workspace, spectator, proposal)
        with pytest.raises(PermissionError):
            list_provisional_changes(workspace, spectator)
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT patch FROM provisional_mobile_changes WHERE id=%s", (proposal,))
        assert cursor.fetchone()["patch"] == {"phone": "123"}


def test_restore_requires_explicit_review_and_applies_phone_field(clean_database):
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug='default'")
        workspace = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO users(email,password_hash,workspace_id) VALUES "
                       "('restore-sync@example.test','hash',%s) RETURNING id", (workspace,))
        user = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO people(name,phone,deleted_at) VALUES ('Person','old',now()) RETURNING id,sync_id")
        person = cursor.fetchone()
        cursor.execute("INSERT INTO provisional_mobile_changes(workspace_id,user_id,device_id,mutation_id,entity_kind,"
                       "entity_sync_id,reason,patch,changed_at,expires_at) VALUES "
                       "(%s,%s,%s,%s,'person',%s,'soft_deleted',%s,%s,now()+interval '30 days') RETURNING id",
                       (workspace, user, str(uuid4()), str(uuid4()), person["sync_id"], Json({"phone": "new"}),
                        datetime.now(UTC) + timedelta(minutes=1)))
        proposal = cursor.fetchone()["id"]
    with workspace_scope(workspace), audit_scope(f"user:{user}", "user", "review-restore"):
        assert restore_provisional_change(workspace, user, proposal) is True
        assert restore_provisional_change(workspace, user, proposal) is False
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT phone,deleted_at FROM people WHERE id=%s", (person["id"],))
        assert dict(cursor.fetchone()) == {"phone": "new", "deleted_at": None}
        cursor.execute("SELECT status,patch FROM provisional_mobile_changes WHERE id=%s", (proposal,))
        assert dict(cursor.fetchone()) == {"status": "applied", "patch": {"phone": "new"}}
        cursor.execute("SELECT count(*) AS n FROM audit_log WHERE action='sync.review_restore' AND target=%s", (f"offline-change:{proposal}",))
        assert cursor.fetchone()["n"] == 1


def test_erased_record_cannot_be_restored_from_review(clean_database):
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug='default'")
        workspace = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO users(email,password_hash,workspace_id) VALUES "
                       "('erased-review@example.test','hash',%s) RETURNING id", (workspace,))
        user = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO people(name,deleted_at) VALUES ('Person',now()) RETURNING id,sync_id")
        person = cursor.fetchone()
        cursor.execute("INSERT INTO provisional_mobile_changes(workspace_id,user_id,device_id,mutation_id,entity_kind,"
                       "entity_sync_id,reason,patch,changed_at,expires_at) VALUES "
                       "(%s,%s,%s,%s,'person',%s,'soft_deleted',%s,now(),now()+interval '30 days') RETURNING id",
                       (workspace, user, str(uuid4()), str(uuid4()), person["sync_id"], Json({"phone": "private"})))
        proposal = cursor.fetchone()["id"]
        cursor.execute("DELETE FROM people WHERE id=%s", (person["id"],))
    with workspace_scope(workspace), audit_scope(f"user:{user}", "user", "review-erasure"):
        assert restore_provisional_change(workspace, user, proposal) is False
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT count(*) AS n FROM provisional_mobile_changes WHERE id=%s", (proposal,))
        assert cursor.fetchone()["n"] == 0


def test_phone_can_read_only_its_own_review_outcomes_without_patch_values(clean_database):
    device, other_device, mutation, entity = uuid4(), uuid4(), uuid4(), uuid4()
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug='default'")
        workspace = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO users(email,password_hash,workspace_id) VALUES "
                       "('phone-review@example.test','hash',%s) RETURNING id", (workspace,))
        user = cursor.fetchone()["id"]
        for registered in (device, other_device):
            cursor.execute("INSERT INTO mobile_sync_devices(workspace_id,user_id,device_id,server_environment,app_version,schema_version) "
                           "VALUES (%s,%s,%s,'production','1',1)", (workspace, user, str(registered)))
        cursor.execute("INSERT INTO sync_mutations(workspace_id,user_id,device_id,mutation_id,entity_kind,entity_sync_id,"
                       "operation,request_hash,status) VALUES (%s,%s,%s,%s,'person',%s,'update','hash','provisional')",
                       (workspace, user, str(device), str(mutation), str(entity)))
        cursor.execute("INSERT INTO provisional_mobile_changes(workspace_id,user_id,device_id,mutation_id,entity_kind,"
                       "entity_sync_id,reason,patch,changed_at,expires_at) VALUES "
                       "(%s,%s,%s,%s,'person',%s,'soft_deleted',%s,now(),now()+interval '30 days')",
                       (workspace, user, str(device), str(mutation), str(entity), Json({"phone": "private"})))
    with workspace_scope(workspace):
        assert read_review_outcomes(workspace, user, str(device), "production", [str(mutation)]) == [
            {"mutation_id": str(mutation), "status": "pending"}]
        assert read_review_outcomes(workspace, user, str(other_device), "production", [str(mutation)]) == []
        with pytest.raises(PermissionError):
            read_review_outcomes(workspace, user, str(uuid4()), "production", [str(mutation)])
        with audit_scope(f"user:{user}", "user", "review-outcome"):
            proposal = list_provisional_changes(workspace, user)[0]["id"]
            assert discard_provisional_change(workspace, user, proposal)
        assert read_review_outcomes(workspace, user, str(device), "production", [str(mutation)]) == [
            {"mutation_id": str(mutation), "status": "discarded"}]


def test_review_applies_only_selected_fields_to_merge_survivor(clean_database):
    device = uuid4()
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug='default'")
        workspace = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO users(email,password_hash,workspace_id) VALUES "
                       "('review-merge@example.test','hash',%s) RETURNING id", (workspace,))
        user = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO mobile_sync_devices(workspace_id,user_id,device_id,server_environment,app_version,schema_version) "
                       "VALUES (%s,%s,%s,'production','1',1)", (workspace, user, str(device)))
        cursor.execute("INSERT INTO people(name,title) VALUES ('Keep','Original'),('Duplicate',NULL) RETURNING id,sync_id")
        keep, duplicate = cursor.fetchall()
    with workspace_scope(workspace), audit_scope(f"user:{user}", "user", "review-merge"):
        merge_people(keep["id"], duplicate["id"], apply=True)
        update = SyncUpdate(mutation_id=uuid4(), device_id=device, entity_kind="person", entity_sync_id=duplicate["sync_id"],
                            operation="update", changed_at=datetime.now(UTC) + timedelta(minutes=1),
                            patch={"phone": "new phone", "title": "Unselected"})
        assert apply_sync_update(workspace, user, "production", update)["status"] == "provisional"
        proposal = list_provisional_changes(workspace, user)[0]["id"]
        with pytest.raises(ValueError):
            apply_merged_provisional_change(workspace, user, proposal, ["phone", "workspace_id"])
        assert apply_merged_provisional_change(workspace, user, proposal, ["phone"])
        assert not apply_merged_provisional_change(workspace, user, proposal, ["phone"])
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT phone,title FROM people WHERE id=%s", (keep["id"],))
        assert dict(cursor.fetchone()) == {"phone": "new phone", "title": "Original"}
        cursor.execute("SELECT status,decision FROM provisional_mobile_changes WHERE id=%s", (proposal,))
        assert dict(cursor.fetchone()) == {"status": "applied", "decision": "merge"}
