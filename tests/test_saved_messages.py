"""Validation preserves user wording and private libraries require real accounts."""
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from gcrm.api.jwt_auth import create_token
from gcrm.api.main import app
from gcrm.api.routers.api_saved_messages import MessageBody, MessageEdit, message_owner

WORDING = "  α\r\n\n🙂\t  "


def test_validated_wording_is_not_trimmed_or_normalized():
    message = MessageBody(title=" label ", body=WORDING)
    assert message.body == WORDING
    assert message.title == " label "


@pytest.mark.parametrize("title, body", [(" ", WORDING), ("label", "\n\t "), ("x" * 101, WORDING), ("label", "x" * 20001)])
def test_blank_or_oversized_messages_are_rejected(title, body):
    with pytest.raises(ValidationError):
        MessageBody(title=title, body=body)


def test_edits_require_a_current_version():
    with pytest.raises(ValidationError):
        MessageEdit(title="label", body=WORDING, version=0)


@pytest.mark.parametrize("payload, user", [({}, None), ({"uid": 42}, None), ({"uid": 42}, {"is_active": False, "workspace_id": 1})])
def test_no_shared_or_inactive_identity_can_access_private_messages(payload, user):
    with patch("gcrm.api.routers.api_saved_messages.get_user_by_id", return_value=user):
        with pytest.raises(HTTPException) as denied:
            message_owner(payload)
    assert denied.value.status_code == 403


def test_private_owner_is_resolved_from_account_not_request_body():
    with patch("gcrm.api.routers.api_saved_messages.get_user_by_id", return_value={"is_active": True, "workspace_id": 7}):
        assert message_owner({"uid": 42}) == (42, 7)


def test_anonymous_and_shared_admin_have_no_library():
    client = TestClient(app)
    assert client.get("/api/saved-messages").status_code == 401
    response = client.get("/api/saved-messages", headers={"Authorization": f"Bearer {create_token('admin')}"})
    assert response.status_code == 403
