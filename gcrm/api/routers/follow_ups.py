"""Web worklist and review of explicit follow-ups."""
from datetime import date, datetime
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from gcrm.api.auth import require_admin, require_login
from gcrm.api.redirects import local_redirect
from gcrm.api.templates import templates
from gcrm.dates import parse_day
from gcrm.organization_state import PIPELINE_STAGES
from gcrm.tools.db_offers import list_offers
from gcrm.tools.follow_up_queries import (
    find_follow_ups,
    list_follow_up_people,
    list_follow_up_targets,
)
from gcrm.tools.follow_ups import (
    change_follow_up_status,
    create_follow_up,
    list_follow_ups,
    resolve_review,
    update_follow_up,
)

router = APIRouter(prefix="/follow-ups", tags=["follow-ups"], dependencies=[Depends(require_login)])
PAGE_SIZE = 25


def parse_date(value: str) -> date | None:
    try:
        return parse_day(value)
    except ValueError as error:
        raise HTTPException(400, "Invalid date") from error


def parse_version(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError as error:
        raise HTTPException(400, "Invalid version") from error


def page_link(page: int, filters: dict) -> str:
    return "/follow-ups/?" + urlencode({**filters, "page": page})


@router.get("/", response_class=HTMLResponse)
def follow_ups_page(request: Request, q: str = Query("", max_length=100), task_type: str = "",
                    stage: str = "", offer: str = "", date_from: str = "", date_to: str = "",
                    direction: str = "asc", view: str = "active", page: int = Query(1, ge=1), target: str = "",
                    task: int | None = None):
    workspace = request.session.get("workspace_id")
    filters = dict(q=q, task_type=task_type, stage=stage, offer=offer or "", date_from=date_from,
                   date_to=date_to, direction=direction, view=view)
    try:
        offer_id = int(offer) if offer else None
        tasks = find_follow_ups(workspace_id=workspace, search=q, task_type=task_type, stage=stage,
                                offer_id=offer_id, date_from=parse_date(date_from), date_to=parse_date(date_to),
                                direction=direction, status=view, limit=PAGE_SIZE + 1, offset=(page - 1) * PAGE_SIZE,
                                task_id=task)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    return templates.TemplateResponse("follow_ups.html", {
        "request": request, "tasks": tasks[:PAGE_SIZE], "filters": filters, "stages": PIPELINE_STAGES,
        "opened_task": task,
        "offers": list_offers(workspace, include_archived=True), "targets": list_follow_up_targets(workspace),
        "people": list_follow_up_people(workspace), "selected_target": target,
        "review_candidates": list_follow_ups(workspace) if view == "review" else [],
        "today": date.today(), "page": page,
        "previous": page_link(page - 1, filters) if page > 1 else None,
        "next_page": page_link(page + 1, filters) if len(tasks) > PAGE_SIZE else None,
    })


@router.post("/new")
def add_follow_up(request: Request, target: str = Form(...), task_type: str = Form(...),
                  task_text: str = Form(...), due_date: str = Form(""), contact_person_id: int | None = Form(None),
                  next: str = Form(""), _admin: str = Depends(require_admin)):
    """Create a follow-up; `next` is the page to come back to (a deal card), else the list."""
    try:
        kind, target_number = target.split(":", 1)
        columns = {"deal": "deal_id", "organization": "contact_id", "person": "person_id"}
        create_follow_up(**{columns[kind]: int(target_number)}, task_type=task_type, task_text=task_text,
                         due_date=parse_date(due_date), contact_person_id=contact_person_id,
                         workspace_id=request.session.get("workspace_id"))
    except (KeyError, ValueError) as error:
        raise HTTPException(400, str(error)) from error
    return local_redirect(next, fallback="/follow-ups/")


@router.post("/{task_id}/edit")
def edit_follow_up(request: Request, task_id: int, version: str = Form(...), task_type: str = Form(...),
                   task_text: str = Form(...), due_date: str = Form(""), deal_id: int = Form(-1),
                   contact_person_id: int = Form(-1), _admin: str = Depends(require_admin)):
    try:
        update_follow_up(task_id, task_type=task_type, task_text=task_text, due_date=parse_date(due_date),
                         version=parse_version(version), deal_id=None if deal_id == 0 else deal_id,
                         contact_person_id=None if contact_person_id == 0 else contact_person_id,
                         workspace_id=request.session.get("workspace_id"))
    except ValueError as error:
        raise HTTPException(409, str(error)) from error
    return RedirectResponse("/follow-ups/", status_code=303)


@router.post("/{task_id}/status")
def update_status(request: Request, task_id: int, status: str = Form(...), version: str = Form(...),
                  next: str = Form(""), _admin: str = Depends(require_admin)):
    try:
        change_follow_up_status(task_id, status, parse_version(version), request.session.get("workspace_id"))
    except ValueError as error:
        raise HTTPException(409, str(error)) from error
    return local_redirect(next, fallback="/follow-ups/")


@router.post("/{task_id}/review")
def review_follow_up(request: Request, task_id: int, decision: str = Form(...), version: str = Form(...),
                     task_type: str = Form(""), task_text: str = Form(""), due_date: str = Form(""),
                     linked_task_id: int | None = Form(None), deal_id: int = Form(-1),
                     contact_person_id: int = Form(-1), _admin: str = Depends(require_admin)):
    try:
        resolve_review(task_id, decision, parse_version(version), task_type=task_type, task_text=task_text,
                       due_date=parse_date(due_date), linked_task_id=linked_task_id,
                       deal_id=None if deal_id == 0 else deal_id,
                       contact_person_id=None if contact_person_id == 0 else contact_person_id,
                       workspace_id=request.session.get("workspace_id"))
    except ValueError as error:
        raise HTTPException(409, str(error)) from error
    return RedirectResponse("/follow-ups/?view=review", status_code=303)
