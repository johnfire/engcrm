"""Account login -> empty library -> add/edit/reload exact messages privately."""
import pytest
from fastapi.testclient import TestClient

from gcrm.api.jwt_auth import create_token
from gcrm.api.main import app
from gcrm.db.connection import db
from gcrm.tools.db_users import create_user

pytestmark = pytest.mark.e2e
WORDING = "  α\r\n\n🙂\t  "


def test_account_library_roundtrip_edit_conflict_and_private_audit(clean_database):
    owner = create_user("library@example.test", "test-only-hash", "admin")
    other = create_user("other@example.test", "test-only-hash", "admin")
    headers = {"Authorization": f"Bearer {create_token('admin', owner)}", "X-Request-ID": "saved-message-test"}
    other_headers = {"Authorization": f"Bearer {create_token('admin', other)}"}
    client = TestClient(app)
    assert client.get("/api/saved-messages", headers=headers).json() == []
    created = client.post("/api/saved-messages", headers=headers, json={"title": "label", "body": WORDING})
    assert created.status_code == 201
    message = created.json()
    assert message["body"] == WORDING
    assert client.get("/api/saved-messages", headers=headers).json() == [message]
    endpoint = f"/api/saved-messages/{message['id']}"
    edited = client.put(endpoint, headers=headers, json={"title": "changed", "body": WORDING + "\n", "version": 1})
    assert edited.status_code == 200 and edited.json()["body"] == WORDING + "\n"
    assert client.put(endpoint, headers=headers, json={"title": "stale", "body": "x", "version": 1}).status_code == 409
    assert client.get("/api/saved-messages", headers=other_headers).json() == []
    assert client.put(endpoint, headers=other_headers, json={"title": "wrong", "body": "x", "version": 2}).status_code == 404
    assert client.get("/api/saved-messages", headers=headers).json() == [edited.json()]
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT actor, correlation_id, outcome FROM audit_log WHERE action LIKE 'saved_message.%' ORDER BY id")
        audits = cursor.fetchall()
        assert len(audits) == 2
        assert all(dict(entry) == {"actor": f"user:{owner}", "correlation_id": "saved-message-test", "outcome": "saved"} for entry in audits)


def test_rejected_blank_message_never_reaches_the_library(clean_database):
    owner = create_user("blank@example.test", "test-only-hash", "admin")
    headers = {"Authorization": f"Bearer {create_token('admin', owner)}"}
    client = TestClient(app)
    assert client.post("/api/saved-messages", headers=headers, json={"title": "label", "body": "\n \t"}).status_code == 422
    assert client.get("/api/saved-messages", headers=headers).json() == []
