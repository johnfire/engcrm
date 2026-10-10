"""Combined contacts for the web list and mobile feed."""
import logging
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from gcrm.api.auth import require_login
from gcrm.api.jwt_auth import require_jwt_payload
from gcrm.api.offer_filter import api_offer_filter, web_offer_filter
from gcrm.api.routers.api_organizations import _personal_identity
from gcrm.api.templates import templates
from gcrm.organization_state import PIPELINE_STAGES
from gcrm.tools.db_contact_counts import get_contact_counts
from gcrm.tools.db_contact_feed import PAGE_SIZE, get_contact_feed, validate_feed_filters

logger = logging.getLogger(__name__)
router = APIRouter(tags=["contact-feed"])


def check_feed_filters(kind: str, stage: str, sort: str) -> None:
    try:
        validate_feed_filters(kind, stage, sort)
    except ValueError as failure:
        raise HTTPException(400, str(failure)) from failure


@router.get("/api/contact-feed/counts")
def mobile_contact_counts(offer: str | None = None, payload: dict = Depends(require_jwt_payload)) -> dict:
    """Contacted this month and since the start; `offer=<slug>` counts only
    contacts logged as being about that offer. Without it, every contact counts."""
    _, workspace_id = _personal_identity(payload)
    try:
        chosen = None if offer in (None, "", "all") else api_offer_filter(offer, workspace_id)
    except ValueError as failure:
        raise HTTPException(400, str(failure)) from failure
    return get_contact_counts(workspace_id, offer=chosen)


@router.get("/api/contact-feed")
def mobile_contacts(search: str = Query("", max_length=100), kind: str = "", stage: str = "",
                    sort: str = "last_contact", page: int = Query(1, ge=1), offer: str | None = None,
                    payload: dict = Depends(require_jwt_payload)) -> list[dict]:
    """Without `offer` this is the Consulting view the installed app expects;
    `offer=<slug>` is that offer's pipeline, `offer=all` every offer."""
    check_feed_filters(kind, stage, sort)
    _, workspace_id = _personal_identity(payload)
    try:
        chosen = api_offer_filter(offer, workspace_id)
    except ValueError as failure:
        raise HTTPException(400, str(failure)) from failure
    return get_contact_feed(search=search, kind=kind, stage=stage, sort=sort, page=page,
                            workspace_id=workspace_id, offer=chosen, only_pitched=offer not in (None, "", "all"))


def safe_contact_counts(workspace_id: int | None, offer: str | None = None) -> dict | None:
    """The counts are a nicety; if they cannot be read the contact list still loads."""
    try:
        return get_contact_counts(workspace_id, offer=offer)
    except Exception:
        logger.exception("contact counts unavailable")
        return None


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
                 offer: str | None = None, page: int = Query(1, ge=1)):
    filters = remember_feed_filters(request, q=q, kind=kind, stage=stage, sort=sort)
    active_offer, offers = web_offer_filter(request, offer)
    contacts = get_contact_feed(**filters, page=page, workspace_id=request.session.get("workspace_id"),
                                extra_row=True, offer=active_offer, only_pitched=active_offer is not None)
    return templates.TemplateResponse("contact_feed.html", {
        "request": request, "contacts": contacts[:PAGE_SIZE], "filters": filters,
        "stages": PIPELINE_STAGES, "page": page, "offers": offers, "active_offer": active_offer,
        "counts": safe_contact_counts(request.session.get("workspace_id"), active_offer),
        "previous": feed_page_link(page - 1, filters) if page > 1 else None,
        "next": feed_page_link(page + 1, filters) if len(contacts) > PAGE_SIZE else None,
    })
