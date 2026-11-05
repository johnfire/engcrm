"""Security regressions through real web/API handlers and PostgreSQL."""
import re
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from gcrm.api.main import app
from gcrm.api.security import hash_password
from gcrm.db.connection import db
from gcrm.tools.db_users import create_user, set_user_active, set_user_password

pytestmark = [pytest.mark.e2e, pytest.mark.security_boundary]
PASSWORD = "Fictional-security-test-password"


def browser(email="owner@example.test"):
    client = TestClient(app, base_url="https://testserver", follow_redirects=False)
    page = client.get("/login")
    token = re.search(r'name="csrf_token" value="([^"]+)"', page.text)
    client.headers["Origin"] = "https://testserver"
    if token:
        client.headers["X-CSRF-Token"] = token.group(1)
    response = client.post("/login", data={"email": email, "password": PASSWORD})
    assert response.status_code == 303, response.text
    page = client.get("/settings")
    token = re.search(r'name="csrf_token" value="([^"]+)"', page.text)
    if token:
        client.headers["X-CSRF-Token"] = token.group(1)
    return client


@pytest.fixture
def owner(clean_database):
    return create_user("owner@example.test", hash_password(PASSWORD), "admin")


@pytest.mark.parametrize("revoke", ["disable", "password", "logout"])
def test_browser_cookie_cannot_be_reused_after_revocation(owner, revoke):
    client = browser()
    cookie = client.cookies.get("session")
    if revoke == "disable":
        set_user_active("owner@example.test", False)
    elif revoke == "password":
        set_user_password("owner@example.test", hash_password("Changed-security-password"))
    else:
        assert client.post("/logout").status_code == 303
    replay = TestClient(app, base_url="https://testserver", follow_redirects=False)
    replay.cookies.set("session", cookie)
    assert replay.get("/users/").status_code in (303, 307, 401)


def test_role_change_takes_effect_without_logging_in_again(owner):
    client = browser()
    with db() as connection:
        connection.cursor().execute("UPDATE users SET role='spectator' WHERE id=%s", (owner,))
    assert client.get("/users/").status_code == 403


def test_expired_browser_session_and_authentication_store_failure_refuse_access(owner):
    client = browser()
    with patch("gcrm.api.browser_sessions.get_web_session", side_effect=RuntimeError("storage down")):
        assert client.get("/users/").status_code == 503
    with db() as connection:
        connection.cursor().execute("UPDATE web_sessions SET expires_at=NOW()-INTERVAL '1 second'")
    assert client.get("/users/").status_code == 307


def test_shared_admin_session_is_revocable_and_bound_to_current_emergency_password(owner, monkeypatch):
    monkeypatch.setattr("gcrm.api.auth.ADMIN_PASSWORD", PASSWORD)
    client = browser("emergency@example.test")
    assert client.get("/users/").status_code == 200
    monkeypatch.setattr("gcrm.api.auth.ADMIN_PASSWORD", "")
    assert client.get("/users/").status_code == 307


def test_native_form_submission_keeps_the_post_body_available_to_the_route(owner):
    client = browser()
    page = client.get("/settings")
    token = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
    response = client.post("/settings/language", headers={"X-CSRF-Token": ""},
                           data={"csrf_token": token, "ui_language": "de"})
    assert response.status_code == 403  # An explicitly wrong header cannot be rescued by a form token.
    del client.headers["X-CSRF-Token"]
    response = client.post("/settings/language", data={"csrf_token": token, "ui_language": "de"})
    assert response.status_code == 200


@pytest.mark.parametrize("headers", [
    {"Origin": "https://sibling.testserver", "Sec-Fetch-Site": "same-site"},
    {"Origin": "https://testserver", "X-CSRF-Token": ""},
    {"Origin": "null"},
])
def test_forged_cookie_authenticated_change_is_refused(owner, headers):
    client = browser()
    response = client.post("/settings/language", data={"ui_language": "de"}, headers=headers)
    assert response.status_code == 403
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT ui_language FROM users WHERE id=%s", (owner,))
        assert cursor.fetchone()["ui_language"] == "en"


def test_legitimate_form_token_and_bearer_write_work(owner):
    client = browser()
    assert client.post("/settings/language", data={"ui_language": "de"}).status_code == 200
    token = client.post("/api/auth/token", json={"email": "owner@example.test", "password": PASSWORD}).json()["token"]
    assert client.patch("/api/account/language", json={"ui_language": "en"},
                        headers={"Authorization": f"Bearer {token}", "Origin": "https://mobile.invalid"}).status_code == 200


def foreign_records():
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("INSERT INTO workspaces(name,slug) VALUES ('Foreign security records','security-foreign') "
                       "ON CONFLICT(slug) DO UPDATE SET name=EXCLUDED.name RETURNING id")
        workspace = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO contacts(name,workspace_id) VALUES ('Private foreign organization',%s) RETURNING id", (workspace,))
        organization = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO people(name,email,contact_id,workspace_id) VALUES ('Private foreign person','private@example.test',%s,%s) RETURNING id", (organization, workspace))
        person = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO people_interactions(person_id,method,note) VALUES (%s,'note','Foreign private note')", (person,))
    return organization, person


def test_foreign_workspace_records_cannot_be_read_or_changed(owner):
    organization, person = foreign_records()
    client = browser()
    token = client.post("/api/auth/token", json={"email": "owner@example.test", "password": PASSWORD}).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get(f"/api/people/{person}", headers=headers).status_code == 404
    assert client.get(f"/api/people/{person}/notes", headers=headers).status_code == 404
    assert client.get(f"/organizations/{organization}").status_code == 404
    response = client.post(f"/api/people/{person}/notes", json={"method": "note", "note": "Intrusion"}, headers=headers)
    assert response.status_code in (403, 404)
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT count(*) AS n FROM people_interactions WHERE person_id=%s", (person,))
        assert cursor.fetchone()["n"] == 1


@pytest.mark.parametrize("queue", ["approvals", "drafts"])
@pytest.mark.parametrize("suppression", ["do_not_contact", "opt_out", "erasure"])
def test_draft_cannot_send_after_recipient_is_suppressed(owner, queue, suppression):
    _, draft = seed_suppressed_draft(owner, queue, suppression)
    client = browser()
    with patch("gcrm.tools.email.send_email", return_value=True) as send:
        response = client.post(f"/{queue}/{draft}/approve")
    assert response.status_code == 403
    send.assert_not_called()
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT status FROM approval_queue WHERE id=%s", (draft,))
        assert cursor.fetchone()["status"] in ("pending", "on_hold")


def seed_suppressed_draft(owner, queue, suppression, person_target=False):
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT workspace_id FROM users WHERE id=%s", (owner,))
        workspace = cursor.fetchone()["workspace_id"]
        cursor.execute("INSERT INTO contacts(name,email,workspace_id) VALUES ('Suppressed recipient','stop@example.test',%s) RETURNING id", (workspace,))
        organization = cursor.fetchone()["id"]
        target, target_id = "contact_id", organization
        if person_target:
            cursor.execute("INSERT INTO people(name,email,contact_id) VALUES ('Recipient','person@example.test',%s) RETURNING id", (organization,))
            target, target_id = "person_id", cursor.fetchone()["id"]
        cursor.execute(f"INSERT INTO approval_queue({target},draft_subject,draft_body,status) VALUES (%s,'Drafted earlier','Fictional email',%s) RETURNING id", (target_id, "pending" if queue == "approvals" else "on_hold"))
        draft = cursor.fetchone()["id"]
        if suppression == "do_not_contact":
            cursor.execute("UPDATE contacts SET do_not_contact=TRUE WHERE id=%s", (organization,))
        elif suppression:
            cursor.execute("INSERT INTO consent_log(contact_id,legal_basis,opt_out,erasure_requested) VALUES (%s,'legitimate_interest',%s,%s)", (organization, suppression == "opt_out", suppression == "erasure"))
    return organization, draft


@pytest.mark.parametrize("suppression", ["do_not_contact", "opt_out", "erasure"])
def test_person_draft_obeys_linked_organization_suppression(owner, suppression):
    _, draft = seed_suppressed_draft(owner, "drafts", suppression, person_target=True)
    client = browser()
    with patch("gcrm.tools.email.send_email", return_value=True) as send:
        response = client.post(f"/drafts/{draft}/approve")
    assert response.status_code == 403
    send.assert_not_called()


@pytest.mark.parametrize("queue", ["approvals", "drafts"])
def test_opt_out_between_review_and_send_is_rechecked(owner, monkeypatch, queue):
    from importlib import import_module

    organization, draft = seed_suppressed_draft(owner, queue, None)
    module = import_module("gcrm.api.routers.approval" if queue == "approvals" else "gcrm.api.routers.drafts")
    permission_check = module.require_draft_permission

    def opt_out_after_review(draft_id):
        permission_check(draft_id)
        with db() as connection:
            connection.cursor().execute("UPDATE contacts SET do_not_contact=TRUE WHERE id=%s", (organization,))

    monkeypatch.setattr(module, "require_draft_permission", opt_out_after_review)
    client = browser()
    with patch("gcrm.tools.email.send_email", return_value=True) as send:
        assert client.post(f"/{queue}/{draft}/approve").status_code == 403
    send.assert_not_called()
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT status FROM approval_queue WHERE id=%s", (draft,))
        assert cursor.fetchone()["status"] == "approved_unsent"


def test_local_mcp_approval_cannot_bypass_suppression(owner):
    import json

    from gcrm.mcp.server import approval_approve

    _, draft = seed_suppressed_draft(owner, "approvals", "opt_out")
    with patch("gcrm.tools.email.send_email", return_value=True) as send:
        assert "error" in json.loads(approval_approve(draft))
    send.assert_not_called()


def test_mobile_role_is_refreshed_and_foreign_parent_links_are_refused(owner):
    foreign_organization, _ = foreign_records()
    client = browser()
    token = client.post("/api/auth/token", json={"email": "owner@example.test", "password": PASSWORD}).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    response = client.post("/api/people", json={"name": "Local person", "contact_id": foreign_organization}, headers=headers)
    assert response.status_code in (403, 404)
    with db() as connection:
        connection.cursor().execute("UPDATE users SET role='spectator' WHERE id=%s", (owner,))
    assert client.post("/api/contacts", json={"name": "Forbidden"}, headers=headers).status_code == 403


def test_second_workspace_can_use_its_own_web_and_mobile_records(owner):
    _, person = foreign_records()
    second_user = create_user("second@example.test", hash_password(PASSWORD), "admin")
    with db() as connection:
        connection.cursor().execute("UPDATE users SET workspace_id=(SELECT workspace_id FROM people WHERE id=%s) WHERE id=%s", (person, second_user))
    client = browser("second@example.test")
    assert client.get(f"/people/{person}").status_code == 200
    users = client.get("/users/")
    assert "second@example.test" in users.text
    assert "owner@example.test" not in users.text
    token = client.post("/api/auth/token", json={"email": "second@example.test", "password": PASSWORD}).json()["token"]
    response = client.get(f"/api/people/{person}", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["email"] == "private@example.test"
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT action,workspace_id FROM audit_log WHERE actor='second@example.test' "
                       "AND action IN ('auth.login','auth.mobile_token_issued')")
        events = cursor.fetchall()
        cursor.execute("SELECT workspace_id FROM people WHERE id=%s", (person,))
        workspace = cursor.fetchone()["workspace_id"]
    assert {event["action"] for event in events} == {"auth.login", "auth.mobile_token_issued"}
    assert all(event["workspace_id"] == workspace for event in events)


def test_two_held_draft_approvals_send_only_once(owner):
    from concurrent.futures import ThreadPoolExecutor
    from time import sleep

    _, draft = seed_suppressed_draft(owner, "drafts", None)
    client = browser()
    clients = [TestClient(app, base_url="https://testserver", cookies=client.cookies,
                          headers=dict(client.headers), follow_redirects=False) for _ in range(2)]

    def send_once(**message):
        sleep(0.1)
        return True

    with patch("gcrm.tools.email.send_email", side_effect=send_once) as send, ThreadPoolExecutor(2) as executor:
        responses = list(executor.map(lambda browser_client: browser_client.post(f"/drafts/{draft}/approve"), clients))
    assert sorted(response.status_code for response in responses) == [303, 404]
    assert send.call_count == 1


def test_invited_signup_and_audit_stay_in_the_invited_workspace(owner):
    from gcrm.tools.db_account_lifecycle import hash_one_time_token

    _, person = foreign_records()
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT workspace_id FROM people WHERE id=%s", (person,))
        workspace = cursor.fetchone()["workspace_id"]
        cursor.execute("INSERT INTO account_invitations(workspace_id,email,role,token_hash,expires_at) "
                       "VALUES (%s,'invited@example.test','spectator',%s,NOW()+INTERVAL '1 day')",
                       (workspace, hash_one_time_token("fictional-invitation-token")))
    client = TestClient(app, base_url="https://testserver", follow_redirects=False)
    page = client.get("/signup")
    token = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
    response = client.post("/signup", data={"email": "invited@example.test", "password": PASSWORD,
                                            "invitation_token": "fictional-invitation-token", "csrf_token": token},
                           headers={"Origin": "https://testserver"})
    assert response.status_code == 303
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id,workspace_id FROM users WHERE email='invited@example.test'")
        account = cursor.fetchone()
        assert account["workspace_id"] == workspace
        cursor.execute("SELECT workspace_id FROM audit_log WHERE action='account.signup' AND target=%s", (f"user:{account['id']}",))
        assert cursor.fetchone()["workspace_id"] == workspace
