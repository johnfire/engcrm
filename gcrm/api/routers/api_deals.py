"""Mobile endpoints for offers and deals (JSON, JWT) — the same operations as
the web Deals panel (gcrm/api/routers/deals.py), for the phone."""
import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from gcrm.api.jwt_auth import require_jwt_admin, require_jwt_payload
from gcrm.api.routers.api_organizations import _personal_identity
from gcrm.organization_state import PIPELINE_STAGES, STATUSES
from gcrm.tools.db_offers import list_offers
from gcrm.tools.deal_money import (
    add_deal_sale,
    deal_money,
    end_subscription,
    set_sale_status,
    set_series_status,
    start_subscription,
)
from gcrm.tools.deal_offer_changes import DealOfferConflict, change_deal_offer
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


def _with_money(deals: list[dict]) -> list[dict]:
    """Each deal with what it earns: {sales_total, sales, subscriptions, running}."""
    money = deal_money([deal["id"] for deal in deals])
    return [{**deal, "money": money[deal["id"]]} for deal in deals]


@router.get("/contacts/{contact_id}/deals")
def organization_deals(contact_id: int, payload: dict = Depends(require_jwt_payload)) -> list[dict]:
    return _with_money(get_deals("organization", contact_id, _workspace(payload)))


@router.get("/people/{person_id}/deals")
def person_deals(person_id: int, payload: dict = Depends(require_jwt_payload)) -> dict:
    """The deals a person owns, and the organizations' deals they are the contact person on."""
    workspace = _workspace(payload)
    return {"owned": _with_money(get_deals("person", person_id, workspace)),
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


class OfferChange(BaseModel):
    offer_id: int = Field(gt=0)


@router.patch("/deals/{deal_id}/offer")
def change_offer(deal_id: int, body: OfferChange, _role: str = Depends(require_jwt_admin),
                 payload: dict = Depends(require_jwt_payload)) -> dict:
    try:
        return change_deal_offer(deal_id, body.offer_id, _workspace(payload))
    except DealNotFound:
        raise HTTPException(status_code=404, detail="Deal or offer not found")
    except DealOfferConflict as conflict:
        raise HTTPException(status_code=409, detail=str(conflict))


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


class Sale(BaseModel):
    amount_eur: Decimal
    won_on: date
    description: str = ""
    status: str = "collected"  # booked | contracted | collected | cancelled
    expected_on: date | None = None  # when it is due; with months, the first payment's day
    months: int = 1  # 2 to 60: a contract paid in that many monthly payments


@router.post("/deals/{deal_id}/sales", status_code=201)
def record_deal_sale(deal_id: int, body: Sale, _role: str = Depends(require_jwt_admin),
                     payload: dict = Depends(require_jwt_payload)) -> dict:
    """A one-off sale on an organization's deal."""
    try:
        return {"id": add_deal_sale(deal_id, body.amount_eur, body.won_on, body.description, _workspace(payload),
                                     status=body.status, expected_on=body.expected_on, months=body.months)}
    except DealNotFound:
        raise HTTPException(status_code=404, detail="Deal not found")
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))


class SaleMove(BaseModel):
    status: str
    collected_on: date | None = None  # the day the money came in; today when left out


@router.patch("/deals/{deal_id}/sales/{sale_id}")
def move_deal_sale(deal_id: int, sale_id: int, body: SaleMove, _role: str = Depends(require_jwt_admin),
                   payload: dict = Depends(require_jwt_payload)) -> dict:
    """Move a sale along: booked → contracted → collected, or cancelled."""
    try:
        if not set_sale_status(deal_id, sale_id, body.status, collected_on=body.collected_on,
                               workspace_id=_workspace(payload)):
            raise HTTPException(status_code=404, detail="Sale not found")
    except DealNotFound:
        raise HTTPException(status_code=404, detail="Deal not found")
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    return {"id": sale_id, "status": body.status}


class SeriesMove(BaseModel):
    status: str


@router.patch("/deals/{deal_id}/series/{series_id}")
def move_deal_series(deal_id: int, series_id: uuid.UUID, body: SeriesMove, _role: str = Depends(require_jwt_admin),
                     payload: dict = Depends(require_jwt_payload)) -> dict:
    """Move a contract's payments that are not yet received to another status (or cancel them)."""
    try:
        changed = set_series_status(deal_id, str(series_id), body.status, workspace_id=_workspace(payload))
    except DealNotFound:
        raise HTTPException(status_code=404, detail="Deal not found")
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    if not changed:
        raise HTTPException(status_code=404, detail="Contract not found")
    return {"changed": changed, "status": body.status}


class SubscriptionStart(BaseModel):
    amount_eur_month: Decimal
    started_on: date
    note: str = ""


@router.post("/deals/{deal_id}/subscription", status_code=201)
def start_deal_subscription(deal_id: int, body: SubscriptionStart, _role: str = Depends(require_jwt_admin),
                            payload: dict = Depends(require_jwt_payload)) -> dict:
    """Start the deal's subscription, or change its price from `started_on`."""
    try:
        return {"id": start_subscription(deal_id, body.amount_eur_month, body.started_on, body.note,
                                         _workspace(payload))}
    except DealNotFound:
        raise HTTPException(status_code=404, detail="Deal not found")
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))


class SubscriptionEnd(BaseModel):
    ended_on: date  # the last day paid for


@router.post("/deals/{deal_id}/subscription/end")
def end_deal_subscription(deal_id: int, body: SubscriptionEnd, _role: str = Depends(require_jwt_admin),
                          payload: dict = Depends(require_jwt_payload)) -> dict:
    try:
        if not end_subscription(deal_id, body.ended_on, _workspace(payload)):
            raise HTTPException(status_code=404, detail="No running subscription")
    except DealNotFound:
        raise HTTPException(status_code=404, detail="Deal not found")
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    return {"ended": True}
