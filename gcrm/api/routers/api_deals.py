"""Mobile endpoints for offers and deals (JSON, JWT) — the same operations as
the web Deals panel (gcrm/api/routers/deals.py), for the phone."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from gcrm.api.jwt_auth import require_jwt_admin, require_jwt_payload
from gcrm.api.routers.api_organizations import _personal_identity
from gcrm.organization_state import PIPELINE_STAGES, STATUSES
from gcrm.tools.db_offers import list_offers
from gcrm.tools.deal_records import (
    DealNotFound,
    add_deal,
    get_deals,
    get_deals_as_contact_person,
    remove_deal,
    set_deal_next_step,
    update_deal,
)

router = APIRouter(prefix="/api", tags=["mobile-deals"])


def _workspace(payload: dict) -> int | None:
    return _personal_identity(payload)[1]


@router.get("/offers")
def offers(payload: dict = Depends(require_jwt_payload)) -> list[dict]:
    """The workspace's active offers, in display order."""
    return [{key: offer[key] for key in ("id", "slug", "name", "website", "revenue_kind")}
            for offer in list_offers(_workspace(payload))]


@router.get("/contacts/{contact_id}/deals")
def organization_deals(contact_id: int, payload: dict = Depends(require_jwt_payload)) -> list[dict]:
    return get_deals("organization", contact_id, _workspace(payload))


@router.get("/people/{person_id}/deals")
def person_deals(person_id: int, payload: dict = Depends(require_jwt_payload)) -> dict:
    """The deals a person owns, and the organizations' deals they are the contact person on."""
    workspace = _workspace(payload)
    return {"owned": get_deals("person", person_id, workspace),
            "contact_person_for": get_deals_as_contact_person(person_id, workspace)}


class NewDeal(BaseModel):
    owner: str  # "organization" or "person"
    owner_id: int
    offer_id: int
    stage: str = "candidate"
    status: str = "none"


@router.post("/deals", status_code=201)
def create_deal(body: NewDeal, _role: str = Depends(require_jwt_admin),
                payload: dict = Depends(require_jwt_payload)) -> dict:
    if body.owner not in ("organization", "person"):
        raise HTTPException(status_code=400, detail="Unknown owner")
    if body.stage not in PIPELINE_STAGES or body.status not in STATUSES:
        raise HTTPException(status_code=400, detail="Unknown stage or status")
    try:
        deal_id = add_deal(body.owner, body.owner_id, body.offer_id, _workspace(payload), body.stage, body.status)
    except DealNotFound:
        raise HTTPException(status_code=404, detail="Not found")
    return {"id": deal_id}


class DealChange(BaseModel):
    """Send only what changed. contact_person_id: null clears it, absent leaves it."""
    stage: str | None = None
    status: str | None = None
    contact_person_id: int | None = None


@router.patch("/deals/{deal_id}")
def change_deal(deal_id: int, body: DealChange, _role: str = Depends(require_jwt_admin),
                payload: dict = Depends(require_jwt_payload)) -> dict:
    if body.stage is not None and body.stage not in PIPELINE_STAGES:
        raise HTTPException(status_code=400, detail="Unknown pipeline stage")
    if body.status is not None and body.status not in STATUSES:
        raise HTTPException(status_code=400, detail="Unknown status")
    changes = {"stage": body.stage, "status": body.status}
    if "contact_person_id" in body.model_fields_set:
        changes["contact_person_id"] = body.contact_person_id
    try:
        return update_deal(deal_id, _workspace(payload), **changes)
    except DealNotFound:
        raise HTTPException(status_code=404, detail="Deal not found")
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))


class NextStep(BaseModel):
    next_step: str | None = None  # blank or null clears it (logged as done)
    next_step_date: date | None = None


@router.put("/deals/{deal_id}/next-step")
def deal_next_step(deal_id: int, body: NextStep, _role: str = Depends(require_jwt_admin),
                   payload: dict = Depends(require_jwt_payload)) -> dict:
    try:
        result = set_deal_next_step(deal_id, body.next_step or "", body.next_step_date, _workspace(payload))
    except DealNotFound:
        raise HTTPException(status_code=404, detail="Deal not found")
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    due = result["next_step_date"]
    return {**result, "next_step_date": due.isoformat() if due else None}


@router.delete("/deals/{deal_id}")
def delete_deal(deal_id: int, _role: str = Depends(require_jwt_admin),
                payload: dict = Depends(require_jwt_payload)) -> dict:
    """Stop pitching the offer: the deal is soft-deleted, its history stays."""
    try:
        remove_deal(deal_id, _workspace(payload))
    except DealNotFound:
        raise HTTPException(status_code=404, detail="Deal not found")
    return {"removed": True}
