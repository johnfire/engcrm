from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Event
from uuid import uuid4

import pytest

from gcrm.audit_context import audit_scope
from gcrm.db.connection import db
from gcrm.sync.contracts import SyncUpdate
from gcrm.tools.db_sync_bootstrap import find_sync_entity
from gcrm.tools.db_sync_push import apply_sync_update
from gcrm.workspace_context import workspace_scope

pytestmark = [pytest.mark.integration, pytest.mark.security_boundary]


def test_private_ratings_use_account_scoped_clocks_and_leave_other_users_unchanged(clean_database):
    device = uuid4()
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug='default'")
        workspace = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO users(email,password_hash,workspace_id) VALUES "
                       "('rating-one@example.test','hash',%s),('rating-two@example.test','hash',%s) RETURNING id", (workspace, workspace))
        first, second = [row["id"] for row in cursor.fetchall()]
        cursor.execute("INSERT INTO mobile_sync_devices(workspace_id,user_id,device_id,server_environment,app_version,schema_version) "
                       "VALUES (%s,%s,%s,'production','1',1)", (workspace, first, str(device)))
        cursor.execute("INSERT INTO contacts(name,phone) VALUES ('Company','old') RETURNING id,sync_id")
        organization = cursor.fetchone()
        cursor.execute("INSERT INTO contact_user_priorities(workspace_id,user_id,contact_id,priority,short_term_value) "
                       "VALUES (%s,%s,%s,3,1),(%s,%s,%s,5,2)",
                       (workspace, first, organization["id"], workspace, second, organization["id"]))
    now = datetime.now(UTC)
    change = SyncUpdate(mutation_id=uuid4(), device_id=device, entity_kind="organization", entity_sync_id=organization["sync_id"],
                        operation="update", changed_at=now + timedelta(minutes=1),
                        patch={"phone": "new", "personal_priority": 1, "short_term_value": 3})
    older = change.model_copy(update={"mutation_id": uuid4(), "changed_at": now - timedelta(minutes=1),
                                     "patch": {"personal_priority": 4}})
    with workspace_scope(workspace), audit_scope(f"user:{first}", "user", "private-rating"):
        assert apply_sync_update(workspace, first, "production", change)["status"] == "applied"
        assert apply_sync_update(workspace, first, "production", older)["status"] == "ignored_older"
        with db() as connection:
            cursor = connection.cursor()
            first_view = find_sync_entity(cursor, workspace, first, "organization", str(organization["sync_id"]))
            second_view = find_sync_entity(cursor, workspace, second, "organization", str(organization["sync_id"]))
    assert first_view["fields"]["phone"] == "new"
    assert first_view["fields"]["personal_priority"] == 1 and first_view["fields"]["short_term_value"] == 3
    assert second_view["fields"]["personal_priority"] == 5 and second_view["fields"]["short_term_value"] == 2
    assert first_view["field_versions"]["personal_priority"]["mutation_id"] == str(change.mutation_id)
    assert second_view["field_versions"]["personal_priority"]["mutation_id"] != str(change.mutation_id)


def test_mobile_rating_waits_for_a_concurrent_web_rating_and_keeps_the_newer_value(clean_database):
    device = uuid4()
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug='default'")
        workspace = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO users(email,password_hash,workspace_id) VALUES ('race@example.test','hash',%s) RETURNING id", (workspace,))
        user = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO mobile_sync_devices(workspace_id,user_id,device_id,server_environment,app_version,schema_version) "
                       "VALUES (%s,%s,%s,'production','1',1)", (workspace, user, str(device)))
        cursor.execute("INSERT INTO contacts(name) VALUES ('Race Company') RETURNING id,sync_id")
        organization = cursor.fetchone()
    change = SyncUpdate(mutation_id=uuid4(), device_id=device, entity_kind="organization", entity_sync_id=organization["sync_id"],
                        operation="update", changed_at=datetime.now(UTC) - timedelta(minutes=1), patch={"personal_priority": 1})
    started = Event()

    def push():
        with workspace_scope(workspace), audit_scope(f"user:{user}", "user", "rating-race"):
            started.set()
            return apply_sync_update(workspace, user, "production", change)

    with ThreadPoolExecutor(max_workers=1) as executor:
        with workspace_scope(workspace), db() as connection:
            cursor = connection.cursor()
            cursor.execute("INSERT INTO contact_user_priorities(workspace_id,user_id,contact_id,priority) VALUES (%s,%s,%s,4)",
                           (workspace, user, organization["id"]))
            future = executor.submit(push)
            assert started.wait(5)
            with pytest.raises(TimeoutError):
                future.result(timeout=0.2)
        result = future.result(timeout=10)
    assert result["status"] == "ignored_older"
    assert result["entity"]["fields"]["personal_priority"] == 4


def test_person_rating_clear_and_invalid_value(clean_database):
    device = uuid4()
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug='default'")
        workspace = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO users(email,password_hash,workspace_id) VALUES ('person-rating@example.test','hash',%s) RETURNING id", (workspace,))
        user = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO mobile_sync_devices(workspace_id,user_id,device_id,server_environment,app_version,schema_version) "
                       "VALUES (%s,%s,%s,'production','1',1)", (workspace, user, str(device)))
        cursor.execute("INSERT INTO people(name) VALUES ('Person') RETURNING id,sync_id")
        person = cursor.fetchone()
    clear = SyncUpdate(mutation_id=uuid4(), device_id=device, entity_kind="person", entity_sync_id=person["sync_id"],
                       operation="update", changed_at=datetime.now(UTC), patch={"value_rating": None})
    invalid = clear.model_copy(update={"mutation_id": uuid4(), "patch": {"value_rating": True}})
    with workspace_scope(workspace), audit_scope(f"user:{user}", "user", "person-rating"):
        result = apply_sync_update(workspace, user, "production", clear)
        assert result["status"] == "applied"
        assert result["entity"]["field_versions"]["value_rating"]["mutation_id"] == str(clear.mutation_id)
        assert apply_sync_update(workspace, user, "production", invalid)["status"] == "rejected_validation"
        with db() as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT target_user_id FROM sync_entity_changes WHERE mutation_id=%s", (str(clear.mutation_id),))
            assert [row["target_user_id"] for row in cursor.fetchall()] == [user]
