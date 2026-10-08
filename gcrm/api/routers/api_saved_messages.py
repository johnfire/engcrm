"""Account-private messages for the mobile LinkedIn copy-and-paste flow."""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from gcrm.api.jwt_auth import require_jwt_payload
from gcrm.audit_context import audit_scope
from gcrm.tools.db_audit import log_audit
from gcrm.tools.db_saved_messages import (
    create_saved_message,
    list_saved_messages,
    owns_saved_message,
    update_saved_message,
)
from gcrm.tools.db_users import get_user_by_id

router = APIRouter(prefix="/api/saved-messages", tags=["mobile-saved-messages"])


class MessageBody(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    body: str = Field(min_length=1, max_length=20000)

    @field_validator("title", "body")
    @classmethod
    def reject_blank_text(cls, text: str) -> str:
        if not text.strip():
            raise ValueError("Text must not be blank")
        return text


class MessageEdit(MessageBody):
    version: int = Field(ge=1)


def message_owner(payload: dict = Depends(require_jwt_payload)) -> tuple[int, int]:
    user_id = payload.get("uid")
    user = get_user_by_id(user_id) if user_id is not None else None
    if not user or not user.get("is_active") or user.get("workspace_id") is None:
        raise HTTPException(403, "Sign in with your personal account to use saved messages.")
    return user_id, user["workspace_id"]


@router.get("")
def get_messages(owner: tuple[int, int] = Depends(message_owner)) -> list[dict]:
    return list_saved_messages(*owner)


@router.post("", status_code=201)
def add_message(body: MessageBody, request: Request, owner: tuple[int, int] = Depends(message_owner)) -> dict:
    with audit_scope(f"user:{owner[0]}", "user", request.state.correlation_id):
        stored = create_saved_message(*owner, body.title, body.body)
        log_audit(None, None, "saved_message.created", f"saved_message:{stored['id']}", "saved")
    return stored


@router.put("/{message_id}")
def edit_message(
    message_id: int, body: MessageEdit, request: Request,
    owner: tuple[int, int] = Depends(message_owner),
) -> dict:
    with audit_scope(f"user:{owner[0]}", "user", request.state.correlation_id):
        stored = update_saved_message(*owner, message_id, body.title, body.body, body.version)
        if stored is None:
            if owns_saved_message(*owner, message_id):
                raise HTTPException(409, "This message changed on another device. Your edits have not been saved.")
            raise HTTPException(404, "Message not found")
        log_audit(None, None, "saved_message.updated", f"saved_message:{message_id}", "saved")
    return stored
