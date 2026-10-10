"""The Offers page: what this workspace sells. Add an offer, rename it, set its
website and whether it earns one-off or monthly, reorder, archive."""
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse

from gcrm.api.auth import require_admin, require_login
from gcrm.api.redirects import local_redirect
from gcrm.api.templates import templates
from gcrm.tools.db_offers import (
    REVENUE_KINDS,
    create_offer,
    list_offers,
    move_offer,
    set_offer_archived,
    update_offer,
)

router = APIRouter(prefix="/offers", tags=["offers"], dependencies=[Depends(require_login)])


@router.get("/", response_class=HTMLResponse)
def offers_page(request: Request, error: str = ""):
    return templates.TemplateResponse("offers.html", {
        "request": request,
        "offers": list_offers(request.session.get("workspace_id"), include_archived=True),
        "revenue_kinds": REVENUE_KINDS,
        "error": error,
    })


@router.post("/")
def offer_add(
    request: Request,
    name: str = Form(""),
    website: str = Form(""),
    revenue_kind: str = Form("one_off"),
    _admin: str = Depends(require_admin),
):
    try:
        create_offer(request.session.get("workspace_id"), name, website, revenue_kind)
    except ValueError:
        return local_redirect("/offers/", error="invalid")
    return local_redirect("/offers/")


@router.post("/{offer_id}")
def offer_edit(
    request: Request,
    offer_id: int,
    name: str = Form(""),
    website: str = Form(""),
    revenue_kind: str = Form("one_off"),
    _admin: str = Depends(require_admin),
):
    try:
        found = update_offer(request.session.get("workspace_id"), offer_id, name, website, revenue_kind)
    except ValueError:
        return local_redirect("/offers/", error="invalid")
    if not found:
        raise HTTPException(status_code=404, detail="Offer not found")
    return local_redirect("/offers/")


@router.post("/{offer_id}/archive")
def offer_archive(request: Request, offer_id: int, archived: str = Form("1"),
                  _admin: str = Depends(require_admin)):
    if not set_offer_archived(request.session.get("workspace_id"), offer_id, archived == "1"):
        raise HTTPException(status_code=404, detail="Offer not found")
    return local_redirect("/offers/")


@router.post("/{offer_id}/move")
def offer_move(request: Request, offer_id: int, direction: str = Form(...),
               _admin: str = Depends(require_admin)):
    try:
        found = move_offer(request.session.get("workspace_id"), offer_id, direction)
    except ValueError:
        raise HTTPException(status_code=400, detail="Direction is up or down")
    if not found:
        raise HTTPException(status_code=404, detail="Offer not found")
    return local_redirect("/offers/")
