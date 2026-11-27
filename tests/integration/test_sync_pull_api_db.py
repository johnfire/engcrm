from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from gcrm.api.jwt_auth import create_token
from gcrm.api.main import app
from gcrm.db.connection import db

pytestmark = [pytest.mark.integration, pytest.mark.security_boundary]


def test_pull_is_ordered_account_scoped_and_erasure_safe(clean_database):
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug='default'")
        workspace = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO users(email,password_hash,workspace_id) VALUES "
                       "('pull-owner@example.test','hash',%s),('pull-other@example.test','hash',%s) RETURNING id",
                       (workspace, workspace))
        owner, other = [row["id"] for row in cursor.fetchall()]
        cursor.execute("INSERT INTO contacts(name) VALUES ('Present'),('Erase me') RETURNING id,sync_id")
        present, erased = cursor.fetchall()
        cursor.execute("INSERT INTO contact_user_priorities(workspace_id,user_id,contact_id,priority) "
                       "VALUES (%s,%s,%s,5)", (workspace, other, present["id"]))
        cursor.execute("DELETE FROM contacts WHERE id=%s", (erased["id"],))
    headers = {"Authorization": f"Bearer {create_token('admin', user_id=owner)}"}
    device_id = str(uuid4())
    with TestClient(app) as client:
        assert client.post("/api/sync/devices", headers=headers, json={"device_id": device_id,
                           "server_environment": "production", "app_version": "1", "schema_version": 1}).status_code == 200
        response = client.get("/api/sync/changes", headers=headers, params={"device_id": device_id, "after": 0})
    assert response.status_code == 200
    page = response.json()
    assert page["has_more"] is False
    changes = page["changes"]
    assert [item["sequence"] for item in changes] == sorted(item["sequence"] for item in changes)
    assert len(changes) == 3
    erased_changes = [item for item in changes if item["sync_id"] == str(erased["sync_id"])]
    assert all(item["operation"] == "hard_erase" and "fields" not in item for item in erased_changes)
    assert "Erase me" not in response.text


def test_pull_pagination_has_no_duplicates_or_skipped_changes(clean_database):
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("INSERT INTO users(email,password_hash,workspace_id) VALUES "
                       "('pull-pages@example.test','hash',(SELECT id FROM workspaces WHERE slug='default')) RETURNING id")
        user_id = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO contacts(name) VALUES ('One'),('Two'),('Three')")
    headers = {"Authorization": f"Bearer {create_token('admin', user_id=user_id)}"}
    device_id = str(uuid4())
    with TestClient(app) as client:
        assert client.post("/api/sync/devices", headers=headers, json={"device_id": device_id,
                           "server_environment": "production", "app_version": "1", "schema_version": 1}).status_code == 200
        cursor_value = 0
        names = []
        for _ in range(3):
            response = client.get("/api/sync/changes", headers=headers,
                                  params={"device_id": device_id, "after": cursor_value, "limit": 1})
            assert response.status_code == 200
            page = response.json()
            names.append(page["changes"][0]["fields"]["name"])
            assert page["next_cursor"] > cursor_value
            cursor_value = page["next_cursor"]
        assert page["has_more"] is False
        empty = client.get("/api/sync/changes", headers=headers,
                           params={"device_id": device_id, "after": cursor_value}).json()
    assert names == ["One", "Two", "Three"]
    assert empty["changes"] == []
    assert empty["next_cursor"] == cursor_value


def test_sales_changes_refresh_only_the_derived_deal_total(clean_database):
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug='default'")
        workspace = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO users(email,password_hash,workspace_id) VALUES "
                       "('sync-value@example.test','hash',%s) RETURNING id", (workspace,))
        user_id = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO contacts(name) VALUES ('Company') RETURNING id")
        organization = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO deals(workspace_id,offer_id,contact_id) "
                       "VALUES (%s,offer_id_for(%s,'consulting'),%s) RETURNING id,sync_id", (workspace, workspace, organization))
        deal = cursor.fetchone()
    headers = {"Authorization": f"Bearer {create_token('admin', user_id=user_id)}"}
    device_id = str(uuid4())
    with TestClient(app) as client:
        assert client.post("/api/sync/devices", headers=headers, json={"device_id": device_id,
                           "server_environment": "production", "app_version": "1", "schema_version": 1}).status_code == 200
        before = client.get("/api/sync/changes", headers=headers, params={"device_id": device_id, "after": 0}).json()["next_cursor"]
        with db() as connection:
            cursor = connection.cursor()
            cursor.execute("INSERT INTO contracts(workspace_id,deal_id,title) VALUES (%s,%s,'Private contract') RETURNING id",
                           (workspace, deal["id"]))
            contract = cursor.fetchone()["id"]            # every sale belongs to a contract (migration 111)
            cursor.execute("INSERT INTO sales(workspace_id,deal_id,contract_id,amount_eur,won_on,status,description) VALUES "
                           "(%s,%s,%s,100,'2026-11-01','booked','private details'),"
                           "(%s,%s,%s,50,'2026-11-01','cancelled','do not sync')",
                           (workspace, deal["id"], contract, workspace, deal["id"], contract))
        response = client.get("/api/sync/changes", headers=headers, params={"device_id": device_id, "after": before})
        assert response.status_code == 200
        changes = response.json()["changes"]
        assert changes and all(change["sync_id"] == str(deal["sync_id"]) for change in changes)
        assert float(changes[-1]["fields"]["total_value"]) == 100
        assert "private details" not in response.text and "do not sync" not in response.text
        with db() as connection:
            cursor = connection.cursor()
            cursor.execute("UPDATE sales SET status='cancelled' WHERE deal_id=%s AND status='booked'", (deal["id"],))
        changed = client.get("/api/sync/changes", headers=headers,
                             params={"device_id": device_id, "after": response.json()["next_cursor"]}).json()["changes"]
        assert changed and float(changed[-1]["fields"]["total_value"]) == 0
