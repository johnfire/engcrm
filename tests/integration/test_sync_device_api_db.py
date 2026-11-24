from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from gcrm.api.jwt_auth import create_token
from gcrm.api.main import app
from gcrm.db.connection import db

pytestmark = [pytest.mark.integration, pytest.mark.security_boundary]


def test_device_registration_is_account_scoped_and_revocation_is_respected(clean_database):
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("INSERT INTO users(email,password_hash,workspace_id) "
                       "VALUES ('sync-device@example.test','hash',"
                       "(SELECT id FROM workspaces WHERE slug='default')) RETURNING id")
        user_id = cursor.fetchone()["id"]
    device_id = str(uuid4())
    body = {"device_id": device_id, "server_environment": "production", "app_version": "1.0", "schema_version": 1}
    headers = {"Authorization": f"Bearer {create_token('admin', user_id=user_id)}"}
    with TestClient(app) as client:
        assert client.post('/api/sync/devices', json=body).status_code == 401
        assert client.post('/api/sync/devices', json=body, headers={"Authorization": f"Bearer {create_token('admin')}"}).status_code == 403
        response = client.post('/api/sync/devices', json=body, headers=headers)
        assert response.status_code == 200
        assert response.json() == {"protocol_version": 1, "bootstrap_required": True}
        assert client.post('/api/sync/devices', json=body, headers=headers).status_code == 200
        with db() as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT count(*) AS total FROM mobile_sync_devices WHERE user_id=%s", (user_id,))
            assert cursor.fetchone()["total"] == 1
            cursor.execute("UPDATE mobile_sync_devices SET revoked_at=now() WHERE user_id=%s", (user_id,))
        assert client.post('/api/sync/devices', json=body, headers=headers).status_code == 403
