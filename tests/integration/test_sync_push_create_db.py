from datetime import UTC, datetime
from uuid import uuid4

import pytest

from gcrm.audit_context import audit_scope
from gcrm.db.connection import db
from gcrm.sync.contracts import SyncCreate
from gcrm.tools.db_sync_create import apply_sync_create
from gcrm.workspace_context import workspace_scope

pytestmark = pytest.mark.integration


def test_offline_person_create_and_retry_have_one_stable_identity(clean_database):
    device_id, person_id = uuid4(), uuid4()
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug='default'")
        workspace = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO users(email,password_hash,workspace_id) VALUES "
                       "('create-sync@example.test','hash',%s) RETURNING id", (workspace,))
        user_id = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO mobile_sync_devices(workspace_id,user_id,device_id,server_environment,app_version,schema_version) "
                       "VALUES (%s,%s,%s,'production','1',1)", (workspace, user_id, str(device_id)))
    mutation = SyncCreate(mutation_id=uuid4(), device_id=device_id, entity_kind="person", entity_sync_id=person_id,
                          operation="create", changed_at=datetime.now(UTC), patch={"name": "Offline person", "phone": "123"})
    with workspace_scope(workspace), audit_scope(f"user:{user_id}", "user", "create-sync"):
        first = apply_sync_create(workspace, user_id, "production", mutation)
        second = apply_sync_create(workspace, user_id, "production", mutation)
    assert first["status"] == second["status"] == "applied"
    assert first["entity"]["server_id"] == second["entity"]["server_id"]
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT count(*) AS n FROM people WHERE sync_id=%s", (str(person_id),))
        assert cursor.fetchone()["n"] == 1


def test_offline_person_note_is_recorded_once_with_original_time(clean_database):
    device_id, note_id = uuid4(), uuid4()
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug='default'")
        workspace = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO users(email,password_hash,workspace_id) VALUES "
                       "('create-note@example.test','hash',%s) RETURNING id", (workspace,))
        user_id = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO mobile_sync_devices(workspace_id,user_id,device_id,server_environment,app_version,schema_version) "
                       "VALUES (%s,%s,%s,'production','1',1)", (workspace, user_id, str(device_id)))
        cursor.execute("INSERT INTO people(name) VALUES ('Person') RETURNING sync_id")
        person_id = cursor.fetchone()["sync_id"]
    edited = datetime(2026, 11, 20, 10, 0, tzinfo=UTC)
    mutation = SyncCreate(mutation_id=uuid4(), device_id=device_id, entity_kind="person_note", entity_sync_id=note_id,
                          operation="create", changed_at=edited, patch={"person_sync_id": str(person_id), "note": "Met offline", "method": "visit"})
    with workspace_scope(workspace), audit_scope(f"user:{user_id}", "user", "create-note"):
        first = apply_sync_create(workspace, user_id, "production", mutation)
        second = apply_sync_create(workspace, user_id, "production", mutation)
    assert first["status"] == second["status"] == "applied"
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT note,occurred_at FROM people_interactions WHERE sync_id=%s", (str(note_id),))
        note = cursor.fetchone()
        assert note["note"] == "Met offline"
        assert note["occurred_at"] == edited
        cursor.execute("SELECT count(*) AS n FROM people_interactions WHERE sync_id=%s", (str(note_id),))
        assert cursor.fetchone()["n"] == 1


def test_offline_organization_activity_preserves_follow_up(clean_database):
    device_id, activity_id = uuid4(), uuid4()
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug='default'")
        workspace = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO users(email,password_hash,workspace_id) VALUES "
                       "('create-activity@example.test','hash',%s) RETURNING id", (workspace,))
        user_id = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO mobile_sync_devices(workspace_id,user_id,device_id,server_environment,app_version,schema_version) "
                       "VALUES (%s,%s,%s,'production','1',1)", (workspace, user_id, str(device_id)))
        cursor.execute("INSERT INTO contacts(name) VALUES ('Company') RETURNING sync_id")
        organization_id = cursor.fetchone()["sync_id"]
    mutation = SyncCreate(mutation_id=uuid4(), device_id=device_id, entity_kind="organization_activity", entity_sync_id=activity_id,
                          operation="create", changed_at=datetime.now(UTC), patch={"organization_sync_id": str(organization_id),
                          "summary": "Visited offline", "method": "in_person", "next_action": "Send details",
                          "next_action_date": "2026-12-01", "follow_up_type": "commitment"})
    with workspace_scope(workspace), audit_scope(f"user:{user_id}", "user", "create-activity"):
        assert apply_sync_create(workspace, user_id, "production", mutation)["status"] == "applied"
        assert apply_sync_create(workspace, user_id, "production", mutation)["status"] == "applied"
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id,summary FROM interactions WHERE sync_id=%s", (str(activity_id),))
        activity = cursor.fetchone()
        assert activity["summary"] == "Visited offline"
        cursor.execute("SELECT task_text,task_type,status FROM follow_ups WHERE source_kind='interaction' AND source_id=%s", (activity["id"],))
        assert dict(cursor.fetchone()) == {"task_text": "Send details", "task_type": "commitment", "status": "active"}


def test_offline_initial_deal_is_limited_to_a_newly_created_owner(clean_database):
    device_id, person_id, deal_id = uuid4(), uuid4(), uuid4()
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug='default'")
        workspace = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO users(email,password_hash,workspace_id) VALUES "
                       "('create-deal@example.test','hash',%s) RETURNING id", (workspace,))
        user_id = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO mobile_sync_devices(workspace_id,user_id,device_id,server_environment,app_version,schema_version) "
                       "VALUES (%s,%s,%s,'production','1',1)", (workspace, user_id, str(device_id)))
    now = datetime.now(UTC)
    person = SyncCreate(mutation_id=uuid4(), device_id=device_id, entity_kind="person", entity_sync_id=person_id,
                        operation="create", changed_at=now, patch={"name": "Offline person"})
    deal = SyncCreate(mutation_id=uuid4(), device_id=device_id, entity_kind="deal", entity_sync_id=deal_id,
                      operation="create", changed_at=now, patch={"person_sync_id": str(person_id),
                      "offer_slug": "consulting", "pipeline_stage": "prospect", "status": "meeting"})
    extra = deal.model_copy(update={"mutation_id": uuid4(), "entity_sync_id": uuid4(),
                                   "patch": {**deal.patch, "offer_slug": "learnwohl"}})
    with workspace_scope(workspace), audit_scope(f"user:{user_id}", "user", "create-deal"):
        assert apply_sync_create(workspace, user_id, "production", person)["status"] == "applied"
        assert apply_sync_create(workspace, user_id, "production", deal)["status"] == "applied"
        assert apply_sync_create(workspace, user_id, "production", deal)["status"] == "applied"
        assert apply_sync_create(workspace, user_id, "production", extra)["status"] == "rejected_validation"
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT count(*) AS n FROM deals WHERE person_id=(SELECT id FROM people WHERE sync_id=%s)", (str(person_id),))
        assert cursor.fetchone()["n"] == 1


def test_offline_note_for_deleted_person_is_provisional_until_erasure(clean_database):
    device_id, note_id = uuid4(), uuid4()
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug='default'")
        workspace = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO users(email,password_hash,workspace_id) VALUES "
                       "('create-deleted-note@example.test','hash',%s) RETURNING id", (workspace,))
        user_id = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO mobile_sync_devices(workspace_id,user_id,device_id,server_environment,app_version,schema_version) "
                       "VALUES (%s,%s,%s,'production','1',1)", (workspace, user_id, str(device_id)))
        cursor.execute("INSERT INTO people(name,deleted_at) VALUES ('Deleted',now()) RETURNING id,sync_id")
        person = cursor.fetchone()
    mutation = SyncCreate(mutation_id=uuid4(), device_id=device_id, entity_kind="person_note", entity_sync_id=note_id,
                          operation="create", changed_at=datetime.now(UTC),
                          patch={"person_sync_id": str(person["sync_id"]), "note": "Keep for review"})
    with workspace_scope(workspace), audit_scope(f"user:{user_id}", "user", "deleted-note"):
        assert apply_sync_create(workspace, user_id, "production", mutation)["status"] == "provisional"
        with db() as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT parent_kind,parent_sync_id,patch FROM provisional_mobile_changes WHERE mutation_id=%s", (str(mutation.mutation_id),))
            proposal = cursor.fetchone()
            assert proposal["parent_kind"] == "person"
            assert str(proposal["parent_sync_id"]) == str(person["sync_id"])
            assert proposal["patch"]["note"] == "Keep for review"
            cursor.execute("DELETE FROM people WHERE id=%s", (person["id"],))
        assert apply_sync_create(workspace, user_id, "production", mutation)["status"] == "erased"
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT count(*) AS n FROM provisional_mobile_changes")
        assert cursor.fetchone()["n"] == 0
