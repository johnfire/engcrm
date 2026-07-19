"""Server-flow smoke coverage using FastAPI TestClient and real PostgreSQL."""
import pytest
from fastapi.testclient import TestClient

from gcrm.api.main import app
from gcrm.api.security import hash_password
from gcrm.db.connection import db
from gcrm.tools.db import create_user, queue_for_approval, save_contact

pytestmark = pytest.mark.e2e


def _fetch_one(query: str, params: tuple) -> dict:
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute(query, params)
        return dict(cursor.fetchone())


def _seed_approval_flow() -> tuple[int, int, str]:
    """Create the users and draft required by the approval flow."""
    admin_password = "correct-horse-battery-staple"
    create_user("admin@example.test", hash_password(admin_password), "admin")
    create_user("spectator@example.test", hash_password("spectator-password"), "spectator")
    contact_id = save_contact(
        "E2E Venue",
        "Munich",
        email="venue@example.test",
        status="cold",
    )
    approval_id = queue_for_approval(contact_id, 0, "Hello", "A test draft.")
    return approval_id, contact_id, admin_password


def _mobile_token(client: TestClient, email: str, password: str) -> str:
    """Exchange a test user's credentials for the mobile bearer token."""
    response = client.post("/api/auth/token", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["token"]


def test_admin_can_approve_unsent_draft_and_mobile_roles_are_enforced(clean_database):
    """Login, approval, JWT access, and spectator authorization work together."""
    approval_id, contact_id, admin_password = _seed_approval_flow()
    client = TestClient(app)

    login_response = client.post(
        "/login",
        data={"email": "admin@example.test", "password": admin_password},
        follow_redirects=False,
    )
    approve_response = client.post(
        f"/approvals/{approval_id}/approve",
        follow_redirects=False,
        headers={"X-Request-ID": "e2e-web-approval"},
    )
    admin_token = _mobile_token(client, "admin@example.test", admin_password)
    spectator_token = _mobile_token(client, "spectator@example.test", "spectator-password")
    contacts_response = client.get(
        "/api/contacts",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    spectator_response = client.post(
        f"/api/approvals/{approval_id}/approve",
        headers={"Authorization": f"Bearer {spectator_token}"},
    )

    approval = _fetch_one("SELECT status FROM approval_queue WHERE id = %s", (approval_id,))
    interaction = _fetch_one("SELECT outcome FROM interactions WHERE contact_id = %s", (contact_id,))
    audit_event = _fetch_one(
        "SELECT actor, correlation_id FROM audit_log WHERE target = %s AND action = 'approval.approve'",
        (f"approval:{approval_id}",),
    )

    assert login_response.status_code == 303
    assert approve_response.status_code == 200
    assert approval["status"] == "approved_unsent"
    assert interaction["outcome"] == "no_reply"
    assert audit_event["actor"] == "admin@example.test"
    assert audit_event["correlation_id"] == "e2e-web-approval"
    assert contacts_response.status_code == 200
    assert contacts_response.json()[0]["id"] == contact_id
    assert spectator_response.status_code == 403
