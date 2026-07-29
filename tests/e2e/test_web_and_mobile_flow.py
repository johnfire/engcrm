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


def test_users_rate_the_same_contact_independently_on_web_and_mobile(clean_database):
    """A web save and mobile save never expose or replace another user's value."""
    password_one = "spectator-one-password"
    password_two = "spectator-two-password"
    create_user(
        "priority-one@example.test",
        hash_password(password_one),
        "spectator",
    )
    create_user(
        "priority-two@example.test",
        hash_password(password_two),
        "spectator",
    )
    contact_id = save_contact("Priority E2E Venue", "Munich", status="cold")

    web_client = TestClient(app)
    login_response = web_client.post(
        "/login",
        data={
            "email": "priority-one@example.test",
            "password": password_one,
        },
        follow_redirects=False,
    )
    web_priority_response = web_client.put(
        f"/contacts/{contact_id}/personal-priority",
        json={"priority": 1},
        headers={"X-Request-ID": "e2e-personal-priority"},
    )

    mobile_client = TestClient(app)
    token_two = _mobile_token(
        mobile_client,
        "priority-two@example.test",
        password_two,
    )
    user_two_before = mobile_client.get(
        f"/api/contacts/{contact_id}",
        headers={"Authorization": f"Bearer {token_two}"},
    )
    user_two_save = mobile_client.put(
        f"/api/contacts/{contact_id}/personal-priority",
        headers={"Authorization": f"Bearer {token_two}"},
        json={"priority": 5},
    )
    token_one = _mobile_token(
        mobile_client,
        "priority-one@example.test",
        password_one,
    )
    user_one_after = mobile_client.get(
        f"/api/contacts/{contact_id}",
        headers={"Authorization": f"Bearer {token_one}"},
    )

    with db() as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT priority
            FROM contact_user_priorities
            WHERE contact_id = %s
            ORDER BY priority
            """,
            (contact_id,),
        )
        stored_priorities = [row["priority"] for row in cursor.fetchall()]

    assert login_response.status_code == 303
    assert web_priority_response.json() == {"personal_priority": 1}
    assert user_two_before.json()["personal_priority"] is None
    assert user_two_save.json() == {"personal_priority": 5}
    assert user_one_after.json()["personal_priority"] == 1
    assert stored_priorities == [1, 5]
