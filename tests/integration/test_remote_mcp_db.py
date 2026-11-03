"""The remote MCP endpoint (/mcp) over HTTP against the real schema: no tool runs without
a live token, and with one the field tools work as that user. The app's lifespan runs
(TestClient as a context manager), as in production."""
import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from gcrm.api.main import app
from gcrm.db.connection import db
from gcrm.mcp.tokens import create_token, revoke_token

pytestmark = pytest.mark.integration

HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


def _rpc(client, method, params=None, token=None, rpc_id=1):
    headers = dict(HEADERS)
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    body = {"jsonrpc": "2.0", "id": rpc_id, "method": method, "params": params or {}}
    return client.post("/mcp/", headers=headers, content=json.dumps(body))


def _initialize(client, token):
    return _rpc(client, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                       "clientInfo": {"name": "test", "version": "1"}}, token=token)


@pytest.fixture
def account(clean_database):
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("INSERT INTO users (email, password_hash, role, workspace_id) "
                       "SELECT 'chris@example.test', 'hash', 'admin', id FROM workspaces WHERE slug = 'default' "
                       "RETURNING id, workspace_id")
        return dict(cursor.fetchone())


def test_no_tool_runs_without_a_live_token(account):
    token = create_token(account["id"], "test")
    with TestClient(app) as client:
        assert _rpc(client, "tools/list").status_code == 401
        assert _rpc(client, "tools/list", token="engcrm_not-a-real-one").status_code == 401
        assert _rpc(client, "tools/list", token="not even our format").status_code == 401
        assert _initialize(client, token).status_code == 200
        with db() as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT id FROM mcp_tokens")
            revoke_token(cursor.fetchone()["id"])
        assert _initialize(client, token).status_code == 401


def test_a_token_lists_only_the_field_tools_and_saves_as_its_user(account):
    token = create_token(account["id"], "test")
    with TestClient(app) as client:
        response = _initialize(client, token)
        assert response.status_code == 200
        assert response.json()["result"]["serverInfo"]["name"] == "engcrm-field"

        tools = _rpc(client, "tools/list", token=token).json()["result"]["tools"]
        assert sorted(t["name"] for t in tools) == [
            "add_organization", "add_person", "businesses_here", "find_organization", "log_activity",
            "set_next_step", "set_ratings", "undo_last", "where_am_i"]

        saved = _rpc(client, "tools/call", {"name": "add_organization",
                                            "arguments": {"name": "Bäckerei Maier", "city": "Landsberg"}},
                     token=token).json()["result"]
        result = saved["structuredContent"] if "structuredContent" in saved else json.loads(saved["content"][0]["text"])
        assert result["saved"] is True and result["said"].startswith("Saved Bäckerei Maier")

        refused = _rpc(client, "tools/call", {"name": "where_am_i", "arguments": {}}, token=token).json()["result"]
        refusal = refused["structuredContent"] if "structuredContent" in refused else json.loads(refused["content"][0]["text"])
        assert "Field mode" in refusal["error"]  # no position yet: said back, not a crash

    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id, workspace_id, source FROM contacts WHERE name = 'Bäckerei Maier'")
        organization = dict(cursor.fetchone())
        cursor.execute("SELECT actor, actor_type FROM audit_log WHERE action = 'mcp.organization_added' "
                       "AND target = %s", (f"organization:{organization['id']}",))
        audit = dict(cursor.fetchone())
    assert organization["workspace_id"] == account["workspace_id"] and organization["source"] == "claude_field"
    # Recorded as the connector acting for this user, not as an anonymous web request.
    assert audit == {"actor": f"mcp:user:{account['id']}", "actor_type": "mcp"}


def test_the_url_works_without_the_trailing_slash(account):
    token = create_token(account["id"], "test")
    with TestClient(app) as client:
        body = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                           "clientInfo": {"name": "test", "version": "1"}}}
        response = client.post("/mcp", headers={**HEADERS, "Authorization": f"Bearer {token}"},
                               content=json.dumps(body), follow_redirects=False)
        assert response.status_code == 200  # not a 307 to http://
        assert client.post("/mcp", headers=HEADERS, content="{}", follow_redirects=False).status_code == 401


def test_too_many_requests_are_refused(account):
    token = create_token(account["id"], "test")
    with TestClient(app) as client, patch("gcrm.mcp.remote._limiter.allow", return_value=False):
        assert _initialize(client, token).status_code == 429
