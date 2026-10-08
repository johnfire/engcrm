"""Authenticated, workspace-scoped profile suggestions for pending scans."""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from gcrm.api.jwt_auth import require_jwt_admin, require_jwt_payload
from gcrm.audit_context import audit_scope
from gcrm.db.connection import db
from gcrm.tools.capture_linkedin import find_capture_profiles
from gcrm.tools.db_audit import log_audit
from gcrm.tools.db_users import get_user_by_id
from gcrm.workspace_context import get_workspace_id, set_workspace_id

router = APIRouter()


class ProfileSearchBody(BaseModel):
    name: str = Field(default="", max_length=200)
    company: str = Field(default="", max_length=300)
    city: str = Field(default="", max_length=200)


def establish_capture_workspace(payload: dict) -> None:
    """Sync auth dependencies cannot propagate ContextVars into the handler."""
    if payload.get("uid") is None:
        return
    user = get_user_by_id(payload["uid"])
    if not user or user.get("workspace_id") is None:
        raise HTTPException(403, "Workspace access required")
    set_workspace_id(user["workspace_id"])


@router.post("/{capture_id}/linkedin-search")
def search_capture_profiles(
    capture_id: int, body: ProfileSearchBody, request: Request,
    _role: str = Depends(require_jwt_admin),
    payload: dict = Depends(require_jwt_payload),
) -> dict:
    establish_capture_workspace(payload)
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT id FROM card_captures WHERE id=%s AND kind IN ('card', 'document') "
            "AND status='pending_review' "
            "AND COALESCE(workspace_id, (SELECT id FROM workspaces WHERE slug='default'))=COALESCE(%s, "
            "(SELECT id FROM workspaces WHERE slug='default'))",
            (capture_id, get_workspace_id()),
        )
        if not cursor.fetchone():
            raise HTTPException(404, "Pending capture not found")
    with audit_scope("agent:capture_linkedin_search", "ai", request.state.correlation_id):
        suggestions = find_capture_profiles(body.name, body.company, body.city)
        log_audit(None, None, "capture.linkedin_searched", f"card_capture:{capture_id}", suggestions["status"])
    return suggestions
