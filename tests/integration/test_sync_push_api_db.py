from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from psycopg2.extras import Json

from gcrm.api.jwt_auth import create_token
from gcrm.api.main import app
from gcrm.api.routers import api_sync
from gcrm.db.connection import db

pytestmark = [pytest.mark.integration, pytest.mark.security_boundary]


def test_push_batch_is_disabled_by_default_and_isolates_invalid_mutations(clean_database, monkeypatch):
    device_id = str(uuid4())
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug='default'")
        workspace = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO users(email,password_hash,workspace_id) VALUES "
                       "('batch@example.test','hash',%s) RETURNING id", (workspace,))
        user_id = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO mobile_sync_devices(workspace_id,user_id,device_id,server_environment,app_version,schema_version) "
                       "VALUES (%s,%s,%s,'production','1',1)", (workspace, user_id, device_id))
        cursor.execute("INSERT INTO contacts(name) VALUES ('Company') RETURNING sync_id")
        sync_id = str(cursor.fetchone()["sync_id"])
    headers = {"Authorization": f"Bearer {create_token('admin', user_id=user_id)}"}
    valid = {"mutation_id": str(uuid4()), "device_id": device_id, "entity_kind": "organization",
             "entity_sync_id": sync_id, "operation": "update",
             "changed_at": (datetime.now(UTC)+timedelta(minutes=1)).isoformat(), "patch": {"phone": "123"}}
    invalid = {**valid, "mutation_id": str(uuid4()), "patch": {"workspace_id": 123}}
    with TestClient(app) as client:
        monkeypatch.setattr(api_sync, "MOBILE_SYNC_WRITES_ENABLED", False)
        assert client.post("/api/sync/push", headers=headers, json={"mutations": [valid]}).status_code == 503
        monkeypatch.setattr(api_sync, "MOBILE_SYNC_WRITES_ENABLED", True)
        response = client.post("/api/sync/push", headers=headers, json={"mutations": [invalid, valid]})
        assert response.status_code == 200
        assert [outcome["status"] for outcome in response.json()["outcomes"]] == ["rejected_validation", "applied"]
        conflict = {**valid, "patch": {"phone": "456"}}
        assert client.post("/api/sync/push", headers=headers, json={"mutations": [conflict]}).status_code == 409
        create = {**valid, "mutation_id": str(uuid4()), "entity_sync_id": str(uuid4()),
                  "entity_kind": "person", "operation": "create", "patch": {"name": "New person"}}
        created = client.post("/api/sync/push", headers=headers, json={"mutations": [create]})
        assert created.status_code == 200
        assert created.json()["outcomes"][0]["status"] == "applied"
        assert client.post("/api/sync/push", headers=headers, json={"mutations": [create]}).json()["outcomes"][0]["status"] == "applied"
        organization_sync_id = str(uuid4())
        organization = {**create, "mutation_id": str(uuid4()), "entity_sync_id": organization_sync_id,
                        "entity_kind": "organization", "patch": {"name": "Offline company"}}
        person = {**create, "mutation_id": str(uuid4()), "entity_sync_id": str(uuid4()),
                  "patch": {"name": "Linked person", "organization_sync_id": organization_sync_id}}
        linked = client.post("/api/sync/push", headers=headers, json={"mutations": [organization, person]})
        assert [outcome["status"] for outcome in linked.json()["outcomes"]] == ["applied", "applied"]
        assert linked.json()["outcomes"][1]["entity"]["fields"]["organization_sync_id"] == organization_sync_id
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT phone FROM contacts WHERE sync_id=%s", (sync_id,))
        assert cursor.fetchone()["phone"] == "123"


def test_review_outcomes_are_scoped_to_the_authenticated_device(clean_database):
    device, mutation, entity = str(uuid4()), str(uuid4()), str(uuid4())
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug='default'")
        workspace = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO users(email,password_hash,workspace_id) VALUES "
                       "('review-api@example.test','hash',%s) RETURNING id", (workspace,))
        user_id = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO mobile_sync_devices(workspace_id,user_id,device_id,server_environment,app_version,schema_version) "
                       "VALUES (%s,%s,%s,'production','1',1)", (workspace, user_id, device))
        cursor.execute("INSERT INTO sync_mutations(workspace_id,user_id,device_id,mutation_id,entity_kind,entity_sync_id,"
                       "operation,request_hash,status) VALUES (%s,%s,%s,%s,'person',%s,'update','hash','provisional')",
                       (workspace, user_id, device, mutation, entity))
        cursor.execute("INSERT INTO provisional_mobile_changes(workspace_id,user_id,device_id,mutation_id,entity_kind,"
                       "entity_sync_id,reason,patch,changed_at,expires_at) VALUES "
                       "(%s,%s,%s,%s,'person',%s,'soft_deleted',%s,now(),now()+interval '30 days')",
                       (workspace, user_id, device, mutation, entity, Json({"phone": "private"})))
    headers = {"Authorization": f"Bearer {create_token('admin', user_id=user_id)}"}
    body = {"device_id": device, "server_environment": "production", "mutation_ids": [mutation]}
    with TestClient(app) as client:
        assert client.post("/api/sync/review-outcomes", json=body).status_code == 401
        response = client.post("/api/sync/review-outcomes", headers=headers, json=body)
        assert response.status_code == 200
        assert response.json() == {"outcomes": [{"mutation_id": mutation, "status": "pending"}]}
        assert client.post("/api/sync/review-outcomes", headers=headers, json={**body, "device_id": str(uuid4())}).status_code == 403
        assert client.post("/api/sync/review-outcomes", headers=headers, json={**body, "mutation_ids": [mutation] * 101}).status_code == 422
