"""The Deals panel on organization and person pages: pitch an offer, move it
along, name the contact person, set its next step, stop pitching it.

Plain forms that come back to the page they were sent from, so the stage and
status selects can submit themselves the moment they are picked."""
import uuid
from datetime import date
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Form, HTTPException, Request

from gcrm.api.auth import require_admin, require_login
from gcrm.api.redirects import local_redirect
from gcrm.dates import parse_day
from gcrm.organization_state import PIPELINE_STAGES, STATUSES
from gcrm.sale_series import amount_and_hours, contract_from_form, contract_hours, typed_number
from gcrm.sale_status import SALE_STATUSES
from gcrm.tools.db_offers import list_offers
from gcrm.tools.deal_money import (
    add_deal_sale,
    deal_money,
    delete_deal_sale,
    delete_subscription,
    end_subscription,
    set_sale_due_day,
    set_sale_status,
    set_sale_work,
    set_series_status,
    set_series_work,
    start_subscription,
)
from gcrm.tools.deal_offer_changes import DealOfferConflict, change_deal_offer
from gcrm.tools.deal_records import (
    DealNotFound,
    add_deal,
    contact_people,
    get_deals,
    get_deals_as_contact_person,
    log_offer_default,
    remove_deal,
    set_deal_next_step,
    update_deal,
)

router = APIRouter(prefix="/deals", tags=["deals"], dependencies=[Depends(require_login)])

OWNER_PAGES = {"organization": "/organizations/{}", "person": "/people/{}"}


def _back(next_url: str, fallback: str) -> str:
    return local_redirect(next_url or fallback, fallback=fallback)



def _required_day(value: str) -> date:
    """A typed day (28.10.2026) that must be there. Raises ValueError."""
    day = parse_day(value)
    if day is None:
        raise ValueError("Enter a day like 28.10.2026")
    return day

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
        deal = update_deal(deal_id, request.session.get("workspace_id"), **changes)
    except DealNotFound:
        raise HTTPException(status_code=404, detail="Deal not found")
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    # back to the list the select was on; its owner's list when `next` is unusable
    return _back(next, "/people/" if deal.get("person_id") else "/organizations/")


@router.post("/{deal_id}/offer")
def deal_offer_change(request: Request, deal_id: int, offer_id: int = Form(..., gt=0),
                      next: str = Form(""), _admin: str = Depends(require_admin)):
    try:
        deal = change_deal_offer(deal_id, offer_id, request.session.get("workspace_id"))
    except DealNotFound:
        raise HTTPException(status_code=404, detail="Deal or offer not found")
    except DealOfferConflict as conflict:
        raise HTTPException(status_code=409, detail=str(conflict))
    return _back(next, "/people/" if deal.get("person_id") else "/organizations/")


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
        due = None if done else parse_day(next_step_date)
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


@router.post("/{deal_id}/sales")
def deal_sale_add(
    request: Request,
    deal_id: int,
    amount_eur: str = Form(""),
    hours: str = Form(""),
    rate: str = Form(""),
    work_from: str = Form(""),
    work_to: str = Form(""),
    won_on: str = Form(...),
    description: str = Form(""),
    status: str = Form("booked"),
    expected_on: str = Form(""),
    schedule: str = Form(""),
    months: int = Form(1),
    next: str = Form(""),
    _admin: str = Depends(require_admin),
):
    """Record a sale on the deal — booked, contracted or already collected. `schedule` is
    "one" (a single payment) or "monthly" (the amount is per month, for `months` months, the
    first due on `expected_on`)."""
    try:
        amount, worked = amount_and_hours(typed_number(amount_eur), typed_number(hours), typed_number(rate))   # per month if monthly
        amount, months = contract_from_form(amount, schedule, months)
        add_deal_sale(deal_id, amount, _required_day(won_on), description[:500],
                      workspace_id=request.session.get("workspace_id"), status=status,
                      expected_on=parse_day(expected_on), months=months,
                      hours=contract_hours(worked, schedule, months),
                      work_from=parse_day(work_from), work_to=parse_day(work_to))
    except DealNotFound:
        raise HTTPException(status_code=404, detail="Deal not found")
    except (InvalidOperation, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error) or "Enter an amount above 0 and a date")
    return _back(next, "/organizations/")


@router.post("/{deal_id}/sales/{sale_id}/status")
def deal_sale_status(
    request: Request,
    deal_id: int,
    sale_id: int,
    status: str = Form(...),
    collected_on: str = Form(""),
    next: str = Form(""),
    _admin: str = Depends(require_admin),
):
    """Move a sale along: booked → contracted → collected (the day the money came
    in; today when blank), or cancelled."""
    try:
        if not set_sale_status(deal_id, sale_id, status, collected_on=parse_day(collected_on),
                               workspace_id=request.session.get("workspace_id")):
            raise HTTPException(status_code=404, detail="Sale not found")
    except DealNotFound:
        raise HTTPException(status_code=404, detail="Deal not found")
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    return _back(next, "/organizations/")


@router.post("/{deal_id}/sales/{sale_id}/due-day")
def deal_sale_due_day(
    request: Request,
    deal_id: int,
    sale_id: int,
    due_on: str = Form(""),
    next: str = Form(""),
    _admin: str = Depends(require_admin),
):
    """Set or change the day a sale is due (a monthly contract's later payments follow from it)."""
    try:
        day = _required_day(due_on)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    try:
        if not set_sale_due_day(deal_id, sale_id, day, request.session.get("workspace_id")):
            raise HTTPException(status_code=404, detail="Sale not found")
    except DealNotFound:
        raise HTTPException(status_code=404, detail="Deal not found")
    return _back(next, "/organizations/")


def _hours_and_rate(hours: str, rate: str):
    """(total, hours) of what the hours-and-rate form sent; ValueError when either is missing or not above 0."""
    return amount_and_hours(None, typed_number(hours), typed_number(rate))


@router.post("/{deal_id}/sales/{sale_id}/work")
def deal_sale_work(
    request: Request,
    deal_id: int,
    sale_id: int,
    hours: str = Form(""),
    rate: str = Form(""),
    work_from: str = Form(""),
    work_to: str = Form(""),
    next: str = Form(""),
    _admin: str = Depends(require_admin),
):
    """Reset a sale that is not yet received to hours of work at a rate per hour (its amount follows), and
    optionally the days the work is done (blank: unchanged)."""
    try:
        _hours_and_rate(hours, rate)
        if not set_sale_work(deal_id, sale_id, typed_number(hours), typed_number(rate), request.session.get("workspace_id"),
                             parse_day(work_from), parse_day(work_to)):
            raise HTTPException(status_code=404, detail="Sale not found")
    except DealNotFound:
        raise HTTPException(status_code=404, detail="Deal not found")
    except (InvalidOperation, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error) or "Enter the hours and the rate per hour")
    return _back(next, "/organizations/")


@router.post("/{deal_id}/series/{series_id}/work")
def deal_series_work(
    request: Request,
    deal_id: int,
    series_id: str,
    hours: str = Form(""),
    rate: str = Form(""),
    work_from: str = Form(""),
    work_to: str = Form(""),
    next: str = Form(""),
    _admin: str = Depends(require_admin),
):
    """Reset a contract to hours of work in all at a rate per hour; its total is spread over the payments
    still to come, on the same due days. Optionally the days the work is done (blank: unchanged)."""
    try:
        series = str(uuid.UUID(series_id))
    except ValueError:
        raise HTTPException(status_code=404, detail="Contract not found")
    try:
        _hours_and_rate(hours, rate)
        if not set_series_work(deal_id, series, typed_number(hours), typed_number(rate), request.session.get("workspace_id"),
                               parse_day(work_from), parse_day(work_to)):
            raise HTTPException(status_code=404, detail="Contract not found")
    except DealNotFound:
        raise HTTPException(status_code=404, detail="Deal not found")
    except (InvalidOperation, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error) or "Enter the hours and the rate per hour")
    return _back(next, "/organizations/")


@router.post("/{deal_id}/series/{series_id}/status")
def deal_series_status(
    request: Request,
    deal_id: int,
    series_id: str,
    status: str = Form(...),
    next: str = Form(""),
    _admin: str = Depends(require_admin),
):
    """Move every payment of a contract that is not yet received (booked → contracted, or
    cancelled, or back). Received payments stay received."""
    try:
        series = str(uuid.UUID(series_id))
    except ValueError:
        raise HTTPException(status_code=404, detail="Contract not found")
    try:
        if not set_series_status(deal_id, series, status, request.session.get("workspace_id")):
            raise HTTPException(status_code=404, detail="Contract not found")
    except DealNotFound:
        raise HTTPException(status_code=404, detail="Deal not found")
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    return _back(next, "/organizations/")


@router.post("/{deal_id}/sales/{sale_id}/delete")
def deal_sale_delete(request: Request, deal_id: int, sale_id: int, next: str = Form(""),
                     _admin: str = Depends(require_admin)):
    """Remove a sale recorded by mistake."""
    try:
        if not delete_deal_sale(deal_id, sale_id, request.session.get("workspace_id")):
            raise HTTPException(status_code=404, detail="Sale not found")
    except DealNotFound:
        raise HTTPException(status_code=404, detail="Deal not found")
    return _back(next, "/organizations/")


@router.post("/{deal_id}/subscription")
def deal_subscription_start(
    request: Request,
    deal_id: int,
    amount_eur_month: str = Form(...),
    started_on: str = Form(...),
    next: str = Form(""),
    _admin: str = Depends(require_admin),
):
    """Start the deal's subscription, or change its price from a day on."""
    try:
        amount = Decimal(amount_eur_month.replace(",", ".").strip())
        start_subscription(deal_id, amount, _required_day(started_on), workspace_id=request.session.get("workspace_id"))
    except DealNotFound:
        raise HTTPException(status_code=404, detail="Deal not found")
    except (InvalidOperation, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error) or "Enter an amount above 0 and a date")
    return _back(next, "/organizations/")


@router.post("/{deal_id}/subscription/end")
def deal_subscription_end(
    request: Request,
    deal_id: int,
    ended_on: str = Form(...),
    next: str = Form(""),
    _admin: str = Depends(require_admin),
):
    """End the running subscription; `ended_on` is the last day paid for."""
    try:
        if not end_subscription(deal_id, _required_day(ended_on), request.session.get("workspace_id")):
            raise HTTPException(status_code=404, detail="No running subscription")
    except DealNotFound:
        raise HTTPException(status_code=404, detail="Deal not found")
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    return _back(next, "/organizations/")


@router.post("/{deal_id}/subscription/{subscription_id}/delete")
def deal_subscription_delete(request: Request, deal_id: int, subscription_id: int, next: str = Form(""),
                             _admin: str = Depends(require_admin)):
    """Remove a mistyped subscription."""
    try:
        if not delete_subscription(deal_id, subscription_id, request.session.get("workspace_id")):
            raise HTTPException(status_code=404, detail="Subscription not found")
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
    offers = list_offers(workspace_id)
    return {
        "deal_owner": owner,
        "deal_owner_id": owner_id,
        "deal_page": page,
        "deals": deals,
        "addable_offers": [o for o in offers if o["id"] not in pitched],
        # the log forms: which offer a new entry is about, preselected when there
        # is exactly one open deal
        "log_offers": offers,
        "log_offer_default": log_offer_default(owner, owner_id),
        "contact_people": contact_people(owner_id) if owner == "organization" else [],
        "contact_person_deals": (get_deals_as_contact_person(owner_id, workspace_id)
                                 if owner == "person" else []),
        "deal_money": deal_money([deal["id"] for deal in deals]),
        "pipeline_stages": PIPELINE_STAGES,
        "statuses": STATUSES,
        "sale_statuses": SALE_STATUSES,
        "today": date.today().isoformat(),
    }
