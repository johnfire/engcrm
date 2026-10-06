"""Regress the SDK's action-scoped authorization bug without a live server."""
import pytest
from langgraph_sdk import Auth


@pytest.mark.parametrize("resource", ["threads", "assistants", "crons"])
def test_resource_authorization_registers_only_the_selected_action(resource):
    auth = Auth()

    async def allow_create(ctx, value):
        return None

    async def deny_other_actions(ctx, value):
        return False

    auth.on(resources=resource, actions="read")(deny_other_actions)
    getattr(auth.on, resource)(actions=["create"])(allow_create)

    # These registered keys are what the API's authorization dispatcher reads.
    assert auth._handlers[(resource, "create")] == [allow_create]
    assert auth._handlers[(resource, "read")] == [deny_other_actions]
    assert (resource, "*") not in auth._handlers
