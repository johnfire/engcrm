"""A browser administrator can inspect and review a provisional phone edit."""

import re
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from gcrm.api.main import app
from gcrm.api.security import hash_password
from gcrm.audit_context import audit_scope
from gcrm.db.connection import db
from gcrm.sync.contracts import SyncUpdate
from gcrm.tools.db_sync_push import apply_sync_update
from gcrm.workspace_context import workspace_scope

pytestmark = pytest.mark.e2e


def test_admin_can_review_and_restore_a_deleted_person(clean_database):
    password, device = "offline-review-test-password", uuid4()
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug='default'")
        workspace = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO users(email,password_hash,workspace_id,role) VALUES "
                       "('offline-review@example.test',%s,%s,'admin') RETURNING id", (hash_password(password), workspace))
        user = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO mobile_sync_devices(workspace_id,user_id,device_id,server_environment,app_version,schema_version) "
                       "VALUES (%s,%s,%s,'production','1',1)", (workspace, user, str(device)))
        cursor.execute("INSERT INTO people(name,deleted_at) VALUES ('Deleted person',now()) RETURNING id,sync_id")
        person = cursor.fetchone()
    mutation = SyncUpdate(mutation_id=uuid4(), device_id=device, entity_kind="person", entity_sync_id=person["sync_id"],
                          operation="update", changed_at=datetime.now(UTC) + timedelta(minutes=1),
                          patch={"phone": "123", "notes": "<script>bad()</script>"})
    with workspace_scope(workspace), audit_scope(f"user:{user}", "user", "offline-review-test"):
        assert apply_sync_update(workspace, user, "production", mutation)["status"] == "provisional"
    with TestClient(app) as browser:
        assert browser.get("/offline-changes/", follow_redirects=False).status_code == 307
        assert browser.post("/login", data={"email": "offline-review@example.test", "password": password}, follow_redirects=False).status_code == 303
        page = browser.get("/offline-changes/?lang=en")
        assert page.status_code == 200
        assert "123" in page.text and "Restore" in page.text
        assert "<script>bad()</script>" not in page.text and "&lt;script&gt;bad()&lt;/script&gt;" in page.text
        with db() as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT id FROM provisional_mobile_changes WHERE mutation_id=%s", (str(mutation.mutation_id),))
            proposal_id = cursor.fetchone()["id"]
        response = browser.post(f"/offline-changes/{proposal_id}/restore", follow_redirects=False)
        assert response.status_code == 303
        assert "123" not in browser.get("/offline-changes/?lang=en").text
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT phone,deleted_at FROM people WHERE id=%s", (person["id"],))
        assert dict(cursor.fetchone()) == {"phone": "123", "deleted_at": None}


@pytest.mark.security_boundary
def test_review_page_requires_admin_and_rejects_requests_without_csrf(clean_database):
    password = "offline-review-test-password"
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug='default'")
        workspace = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO users(email,password_hash,workspace_id,role) VALUES "
                       "('admin-review@example.test',%s,%s,'admin'),('viewer-review@example.test',%s,%s,'spectator')",
                       (hash_password(password), workspace, hash_password(password), workspace))
    with TestClient(app) as browser:
        login = browser.get("/login")
        csrf = re.search(r'<meta name="csrf-token" content="([^"]+)"', login.text).group(1)
        headers = {"Origin": str(browser.base_url).rstrip("/"), "X-CSRF-Token": csrf}
        assert browser.post("/login", data={"email": "viewer-review@example.test", "password": password},
                            headers=headers, follow_redirects=False).status_code == 303
        assert browser.get("/offline-changes/", follow_redirects=False).status_code == 403
    with TestClient(app) as browser:
        login = browser.get("/login")
        csrf = re.search(r'<meta name="csrf-token" content="([^"]+)"', login.text).group(1)
        headers = {"Origin": str(browser.base_url).rstrip("/"), "X-CSRF-Token": csrf}
        assert browser.post("/login", data={"email": "admin-review@example.test", "password": password},
                            headers=headers, follow_redirects=False).status_code == 303
        assert browser.post("/offline-changes/1/discard", follow_redirects=False).status_code == 403
