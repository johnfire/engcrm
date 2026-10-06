"""Combined contacts for the web list and mobile feed."""
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from gcrm.api.auth import require_login
from gcrm.api.jwt_auth import require_jwt_payload
from gcrm.api.routers.api_organizations import _personal_identity
from gcrm.api.templates import templates
from gcrm.organization_state import PIPELINE_STAGES
from gcrm.tools.db_contact_feed import PAGE_SIZE, get_contact_feed, validate_feed_filters

router = APIRouter(tags=["contact-feed"])


def check_feed_filters(kind: str, stage: str, sort: str) -> None:
    try:
        validate_feed_filters(kind, stage, sort)
    except ValueError as failure:
        raise HTTPException(400, str(failure)) from failure


@router.get("/api/contact-feed")
def mobile_contacts(search: str = Query("", max_length=100), kind: str = "", stage: str = "",
                    sort: str = "last_contact", page: int = Query(1, ge=1),
                    payload: dict = Depends(require_jwt_payload)) -> list[dict]:
    check_feed_filters(kind, stage, sort)
    _, workspace_id = _personal_identity(payload)
    return get_contact_feed(search=search, kind=kind, stage=stage, sort=sort,
                            page=page, workspace_id=workspace_id)


def remember_feed_filters(request: Request, **selections) -> dict:
    saved = request.session.get("contact_feed_filters", {})
    filters = {key: selected if selected is not None else saved.get(key, default)
               for key, selected, default in (
                   ("search", selections["q"], ""), ("kind", selections["kind"], ""),
                   ("stage", selections["stage"], ""), ("sort", selections["sort"], "last_contact"),
               )}
    if filters["sort"] == "newest":
        filters["sort"] = "last_contact"
    check_feed_filters(filters["kind"], filters["stage"], filters["sort"])
    request.session["contact_feed_filters"] = filters
    return filters


def feed_page_link(page: int, filters: dict) -> str:
    return "/contact-feed/?" + urlencode({"q": filters["search"], "kind": filters["kind"],
                                        "stage": filters["stage"], "sort": filters["sort"], "page": page})


@router.get("/contact-feed/", response_class=HTMLResponse, dependencies=[Depends(require_login)])
def web_contacts(request: Request, q: str | None = Query(None, max_length=100),
                 kind: str | None = None, stage: str | None = None, sort: str | None = None,
                 page: int = Query(1, ge=1)):
    filters = remember_feed_filters(request, q=q, kind=kind, stage=stage, sort=sort)
    contacts = get_contact_feed(**filters, page=page, workspace_id=request.session.get("workspace_id"),
                                extra_row=True)
    return templates.TemplateResponse("contact_feed.html", {
        "request": request, "contacts": contacts[:PAGE_SIZE], "filters": filters,
        "stages": PIPELINE_STAGES, "page": page,
        "previous": feed_page_link(page - 1, filters) if page > 1 else None,
        "next": feed_page_link(page + 1, filters) if len(contacts) > PAGE_SIZE else None,
    })
