"""The Deals panel on organization and person pages: pitch an offer, move it
along, name the contact person, set its next step, stop pitching it.

Plain forms that come back to the page they were sent from, so the stage and
status selects can submit themselves the moment they are picked."""
from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException, Request

from gcrm.api.auth import require_admin, require_login
from gcrm.api.redirects import local_redirect
from gcrm.organization_state import PIPELINE_STAGES, STATUSES
from gcrm.tools.db_offers import list_offers
from gcrm.tools.deal_records import (
    DealNotFound,
    add_deal,
    contact_people,
    get_deals,
    get_deals_as_contact_person,
    remove_deal,
    set_deal_next_step,
    update_deal,
)

router = APIRouter(prefix="/deals", tags=["deals"], dependencies=[Depends(require_login)])

OWNER_PAGES = {"organization": "/organizations/{}", "person": "/people/{}"}


def _back(next_url: str, fallback: str) -> str:
    return local_redirect(next_url or fallback, fallback=fallback)


@router.post("/new")
def deal_add(
    request: Request,
    owner: str = Form(...),
    owner_id: int = Form(...),
    offer_id: int = Form(...),
    _admin: str = Depends(require_admin),
):
    if owner not in OWNER_PAGES:
        raise HTTPException(status_code=400, detail="Unknown owner")
    try:
        add_deal(owner, owner_id, offer_id, request.session.get("workspace_id"))
    except DealNotFound:
        raise HTTPException(status_code=404, detail="Not found")
    page = OWNER_PAGES[owner].format(owner_id)
    return local_redirect(page, fallback=page)


@router.post("/{deal_id}")
def deal_update(
    request: Request,
    deal_id: int,
    stage: str = Form(""),
    status: str = Form(""),
    contact_person_id: str | None = Form(None),
    next: str = Form(""),
    _admin: str = Depends(require_admin),
):
    """Whatever the form sent: a blank stage or status leaves it as it is.
    Contact person 0 clears it — a blank field would arrive as "not sent"."""
    if stage and stage not in PIPELINE_STAGES:
        raise HTTPException(status_code=400, detail="Unknown pipeline stage")
    if status and status not in STATUSES:
        raise HTTPException(status_code=400, detail="Unknown status")
    changes = {"stage": stage or None, "status": status or None}
    if contact_person_id is not None:
        try:
            changes["contact_person_id"] = int(contact_person_id) or None
        except ValueError:
            raise HTTPException(status_code=400, detail="Unknown contact person")
    try:
        update_deal(deal_id, request.session.get("workspace_id"), **changes)
    except DealNotFound:
        raise HTTPException(status_code=404, detail="Deal not found")
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    return _back(next, "/organizations/")


@router.post("/{deal_id}/next-step")
def deal_next_step(
    request: Request,
    deal_id: int,
    next_step: str = Form(""),
    next_step_date: str = Form(""),
    done: str = Form(""),
    next: str = Form(""),
    _admin: str = Depends(require_admin),
):
    """Set the deal's next step, or with `done`, clear it (logged as done)."""
    try:
        due = date.fromisoformat(next_step_date) if next_step_date.strip() and not done else None
        set_deal_next_step(deal_id, "" if done else next_step, due, request.session.get("workspace_id"))
    except DealNotFound:
        raise HTTPException(status_code=404, detail="Deal not found")
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    return _back(next, "/organizations/")


@router.post("/{deal_id}/remove")
def deal_remove(request: Request, deal_id: int, next: str = Form(""), _admin: str = Depends(require_admin)):
    try:
        remove_deal(deal_id, request.session.get("workspace_id"))
    except DealNotFound:
        raise HTTPException(status_code=404, detail="Deal not found")
    return _back(next, "/organizations/")


def panel_context(request: Request, owner: str, owner_id: int, page: str) -> dict:
    """Everything partials/deals_panel.html needs, for an organization's or a
    person's page. The panel is part of the page, so a failure here fails it —
    the stage lives nowhere else any more."""
    workspace_id = request.session.get("workspace_id")
    deals = get_deals(owner, owner_id, workspace_id)
    pitched = {deal["offer_id"] for deal in deals}
    return {
        "deal_owner": owner,
        "deal_owner_id": owner_id,
        "deal_page": page,
        "deals": deals,
        "addable_offers": [o for o in list_offers(workspace_id) if o["id"] not in pitched],
        "contact_people": contact_people(owner_id) if owner == "organization" else [],
        "contact_person_deals": (get_deals_as_contact_person(owner_id, workspace_id)
                                 if owner == "person" else []),
        "pipeline_stages": PIPELINE_STAGES,
        "statuses": STATUSES,
        "today": date.today().isoformat(),
    }
