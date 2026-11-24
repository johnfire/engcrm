from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from gcrm.api.jwt_auth import create_token
from gcrm.api.main import app
from gcrm.db.connection import db

pytestmark = [pytest.mark.integration, pytest.mark.security_boundary]


def test_bootstrap_pages_active_records_without_leaking_internal_columns(clean_database):
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("INSERT INTO users(email,password_hash,workspace_id) VALUES "
                       "('sync-bootstrap@example.test','hash',(SELECT id FROM workspaces WHERE slug='default')) RETURNING id")
        user_id = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO contacts(name,phone) VALUES ('First','111'),('Second','222')")
    headers = {"Authorization": f"Bearer {create_token('admin', user_id=user_id)}"}
    device_id = str(uuid4())
    registration = {"device_id": device_id, "server_environment": "production", "app_version": "1", "schema_version": 1}
    with TestClient(app) as client:
        assert client.post("/api/sync/devices", headers=headers, json=registration).status_code == 200
        response = client.get("/api/sync/bootstrap", headers=headers, params={"device_id": device_id, "limit": 1})
        assert response.status_code == 200
        first = response.json()
        assert len(first["entities"]) == 1
        assert first["entities"][0]["entity_kind"] == "organization"
        assert first["entities"][0]["fields"]["name"] == "First"
        assert "google_data" not in first["entities"][0]["fields"]
        assert first["next_token"]
        response = client.get("/api/sync/bootstrap", headers=headers,
                              params={"device_id": device_id, "limit": 1, "token": first["next_token"]})
        assert response.status_code == 200
        second = response.json()
        assert second["entities"][0]["fields"]["name"] == "Second"
        assert second["high_water"] == first["high_water"]
        response = client.get("/api/sync/bootstrap", headers=headers,
                              params={"device_id": device_id, "token": first["next_token"] + "tampered"})
        assert response.status_code == 400


def test_bootstrap_includes_history_and_only_current_users_ratings(clean_database):
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug='default'")
        workspace = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO users(email,password_hash,workspace_id) VALUES "
                       "('sync-owner@example.test','hash',%s),('sync-other@example.test','hash',%s) RETURNING id",
                       (workspace, workspace))
        owner, other = [row["id"] for row in cursor.fetchall()]
        cursor.execute("INSERT INTO contacts(name) VALUES ('Company') RETURNING id")
        organization = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO people(name,contact_id) VALUES ('Person',%s) RETURNING id", (organization,))
        person = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO deals(workspace_id,offer_id,person_id,pipeline_stage) "
                       "VALUES (%s,offer_id_for(%s,'consulting'),%s,'prospect')", (workspace, workspace, person))
        cursor.execute("INSERT INTO people(name,deleted_at) VALUES ('Deleted person',now()) RETURNING id")
        deleted_person = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO deals(workspace_id,offer_id,person_id,pipeline_stage) "
                       "VALUES (%s,offer_id_for(%s,'consulting'),%s,'suspect')", (workspace, workspace, deleted_person))
        cursor.execute("INSERT INTO people_interactions(person_id,note) VALUES (%s,'A note')", (person,))
        cursor.execute("INSERT INTO interactions(contact_id,interaction_date,summary) VALUES (%s,current_date,'A visit')", (organization,))
        cursor.execute("INSERT INTO contact_user_priorities(workspace_id,user_id,contact_id,priority) "
                       "VALUES (%s,%s,%s,1),(%s,%s,%s,5)", (workspace, owner, organization, workspace, other, organization))
    headers = {"Authorization": f"Bearer {create_token('admin', user_id=owner)}"}
    device_id = str(uuid4())
    with TestClient(app) as client:
        assert client.post("/api/sync/devices", headers=headers, json={"device_id": device_id,
                           "server_environment": "production", "app_version": "1", "schema_version": 1}).status_code == 200
        page = client.get("/api/sync/bootstrap", headers=headers, params={"device_id": device_id}).json()
    entities = page["entities"]
    assert {entry["entity_kind"] for entry in entities} >= {"organization", "person", "deal", "organization_activity", "person_note"}
    company = next(entry for entry in entities if entry["entity_kind"] == "organization")
    assert company["fields"]["personal_priority"] == 1
    assert all(key in company["fields"] for key in company["field_versions"])
    assert len([entry for entry in entities if entry["entity_kind"] == "deal"]) == 1


def test_bootstrap_continuation_is_bound_to_device_and_later_writes_can_be_pulled(clean_database):
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("INSERT INTO users(email,password_hash,workspace_id) VALUES "
                       "('bootstrap-cursor@example.test','hash',(SELECT id FROM workspaces WHERE slug='default')) RETURNING id")
        user_id = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO contacts(name) VALUES ('Before')")
    headers = {"Authorization": f"Bearer {create_token('admin', user_id=user_id)}"}
    first_device, other_device = str(uuid4()), str(uuid4())
    with TestClient(app) as client:
        for device_id in (first_device, other_device):
            assert client.post("/api/sync/devices", headers=headers, json={"device_id": device_id,
                               "server_environment": "production", "app_version": "1", "schema_version": 1}).status_code == 200
        first = client.get("/api/sync/bootstrap", headers=headers,
                           params={"device_id": first_device, "limit": 1}).json()
        rejected = client.get("/api/sync/bootstrap", headers=headers,
                              params={"device_id": other_device, "token": first["next_token"]})
        assert rejected.status_code == 400
        with db() as connection:
            connection.cursor().execute("INSERT INTO contacts(name) VALUES ('After')")
        changes = client.get("/api/sync/changes", headers=headers,
                             params={"device_id": first_device, "after": first["high_water"]}).json()
    assert [change["fields"]["name"] for change in changes["changes"]] == ["After"]
