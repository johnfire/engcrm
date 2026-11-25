"""Admin review of phone changes aimed at deleted or merged records."""

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from gcrm.api.auth import require_admin
from gcrm.api.templates import templates
from gcrm.tools.db_sync_review import (
    apply_merged_provisional_change,
    discard_provisional_change,
    list_provisional_changes,
    restore_provisional_change,
)

router = APIRouter(prefix="/offline-changes", tags=["offline-changes"], dependencies=[Depends(require_admin)])


def _identity(request: Request) -> tuple[int, int]:
    workspace, user = request.session.get("workspace_id"), request.session.get("user_id")
    if not isinstance(workspace, int) or not isinstance(user, int):
        raise HTTPException(403, "A personal workspace administrator is required")
    return workspace, user


@router.get("/", response_class=HTMLResponse)
def review_page(request: Request):
    workspace, user = _identity(request)
    try:
        items = list_provisional_changes(workspace, user)
    except PermissionError as error:
        raise HTTPException(403, str(error)) from error
    return templates.TemplateResponse("offline_changes.html", {"request": request, "items": items})


def _review_result(action, workspace: int, user: int, proposal_id: int, *args):
    try:
        changed = action(workspace, user, proposal_id, *args)
    except PermissionError as error:
        raise HTTPException(403, str(error)) from error
    except ValueError as error:
        raise HTTPException(409, str(error)) from error
    if not changed:
        raise HTTPException(409, "This change is no longer awaiting review")
    return RedirectResponse("/offline-changes/", status_code=303)


@router.post("/{proposal_id}/restore")
def restore(request: Request, proposal_id: int):
    workspace, user = _identity(request)
    return _review_result(restore_provisional_change, workspace, user, proposal_id)


@router.post("/{proposal_id}/discard")
def discard(request: Request, proposal_id: int):
    workspace, user = _identity(request)
    return _review_result(discard_provisional_change, workspace, user, proposal_id)


@router.post("/{proposal_id}/merge")
def apply_to_survivor(request: Request, proposal_id: int, fields: list[str] = Form(default=[])):
    workspace, user = _identity(request)
    return _review_result(apply_merged_provisional_change, workspace, user, proposal_id, fields)
