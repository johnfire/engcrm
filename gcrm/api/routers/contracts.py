"""Contracts: the list of deals made, grouped by when they run, and one contract's page.

Everyone signed in can look; every change needs an admin. Every figure is worked out from the contract's
payments (gcrm/contract_math.py), so it matches the Forecast. Every handler works inside the signed-in account's
own workspace: a contract of another workspace, or a deleted one, is a 404 on every route here."""
from datetime import date
from decimal import InvalidOperation
from typing import Callable, Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from gcrm.api.auth import require_admin, require_login
from gcrm.api.offer_filter import web_offer_filter
from gcrm.api.redirects import local_redirect
from gcrm.api.session_workspace import session_workspace_id
from gcrm.api.templates import templates
from gcrm.contract_input import ContractInputError
from gcrm.contract_kinds import CONTRACT_KINDS
from gcrm.contract_math import SECTIONS, SORT_KEYS, group_by_timing, totals
from gcrm.dates import parse_day
from gcrm.i18n import DEFAULT_LANGUAGE, translate
from gcrm.sale_series import typed_number
from gcrm.sale_status import SALE_STATUSES
from gcrm.tools.db_contracts import (
    ContractNotFound,
    add_link,
    add_payment,
    delete_contract,
    get_contract,
    list_contracts,
    move_link,
    remove_link,
    update_contract,
)
from gcrm.workspace_context import workspace_scope

router = APIRouter(tags=["contracts"], dependencies=[Depends(require_login)])


@router.get("/contracts/", response_class=HTMLResponse)
def contracts_page(
    request: Request,
    offer: Optional[str] = Query(default=None),
    kind: Optional[str] = Query(default=None),
    sort: Optional[str] = Query(default=None),
    dir: Optional[str] = Query(default=None),
):
    """The contracts in their three sections. `sort` (customer, kind, dates or value) and `dir` (asc or desc)
    order each section; without a known sort the sections keep their timing order."""
    active_offer, offers = web_offer_filter(request, offer)
    kind = kind if kind in CONTRACT_KINDS else None            # an unknown kind shows every kind
    sort = sort if sort in SORT_KEYS else None                 # an unknown sort keeps the timing order
    direction = "desc" if dir == "desc" else "asc"
    workspace_id = session_workspace_id(request)
    with workspace_scope(workspace_id):
        contracts = list_contracts(workspace_id, active_offer, kind)
    groups = group_by_timing(contracts, date.today(), sort=sort, descending=direction == "desc")
    sections = [{"key": key, "contracts": groups[key], "totals": totals(groups[key])} for key in SECTIONS]
    return templates.TemplateResponse("contracts.html", {
        "request": request, "sections": sections, "totals": totals(contracts), "kinds": CONTRACT_KINDS,
        "active_kind": kind, "offers": offers, "active_offer": active_offer,
        "sort_keys": SORT_KEYS, "active_sort": sort, "active_dir": direction,
    })


# --- one contract ---------------------------------------------------------------

def _render(request: Request, contract_id: int, open_section: str | None = None, error: str | None = None,
            error_form: str | None = None, status_code: int = 200):
    workspace_id = session_workspace_id(request)
    try:
        with workspace_scope(workspace_id):
            contract = get_contract(contract_id, workspace_id)
    except ContractNotFound:
        raise HTTPException(status_code=404, detail="Contract not found")
    page = f"/contracts/{contract_id}?open=payments"
    payments = contract["payments"]
    live = len(payments)
    for payment in payments:
        # Deleting the last payment (or the last series) deletes the contract itself: go to the list then, not to a 404.
        in_series = sum(1 for other in payments if payment["series_id"] and other["series_id"] == payment["series_id"])
        payment["delete_next"] = "/contracts/" if live == 1 else page
        if payment["series_id"]:
            payment["series_delete_next"] = "/contracts/" if in_series == live else page
    return templates.TemplateResponse("contract_detail.html", {
        "request": request, "c": contract, "kinds": CONTRACT_KINDS, "page": page,
        "is_admin": request.session.get("role") == "admin", "sale_statuses": SALE_STATUSES,
        "today": date.today().isoformat(), "payments_open": open_section == "payments" or error_form == "payment",
        "error": error, "error_form": error_form,
    }, status_code=status_code)


@router.get("/contracts/{contract_id}", response_class=HTMLResponse)
def contract_page(request: Request, contract_id: int, open: Optional[str] = Query(default=None)):
    return _render(request, contract_id, open_section=open)


def _write(request: Request, contract_id: int, action: Callable[[int], None], form: str, then: str | None = None):
    """Run a change inside the workspace, then go back to the contract's page. A contract that is not there is a 404;
    an entry that is refused shows the page again with the reason (status 400) and nothing changed."""
    workspace_id = session_workspace_id(request)
    try:
        with workspace_scope(workspace_id):
            action(workspace_id)
    except ContractNotFound:
        raise HTTPException(status_code=404, detail="Contract not found")
    except ValueError as error:
        lang = request.session.get("ui_language", DEFAULT_LANGUAGE)
        message = translate(error.key, lang) if isinstance(error, ContractInputError) else str(error)
        return _render(request, contract_id, error=message, error_form=form, status_code=400)
    return local_redirect(then or f"/contracts/{contract_id}")


@router.post("/contracts/{contract_id}")
def contract_edit(
    request: Request,
    contract_id: int,
    title: str = Form(""),
    kind: str = Form(""),
    assignment: str = Form(""),
    contact_person_id: str = Form(""),
    _admin: str = Depends(require_admin),
):
    def change(workspace_id: int) -> None:
        try:
            person = int(contact_person_id) if contact_person_id.strip() else None
        except ValueError:
            raise ContractInputError("the contact person must be chosen from the list", "contractPage.error.contact")
        update_contract(contract_id, workspace_id, title, kind, assignment, person)
    return _write(request, contract_id, change, "edit")


@router.post("/contracts/{contract_id}/delete")
def contract_delete(request: Request, contract_id: int, _admin: str = Depends(require_admin)):
    return _write(request, contract_id, lambda workspace_id: delete_contract(contract_id, workspace_id), "delete", then="/contracts/")


@router.post("/contracts/{contract_id}/links")
def contract_link_add(request: Request, contract_id: int, label: str = Form(""), url: str = Form(""),
                      _admin: str = Depends(require_admin)):
    return _write(request, contract_id, lambda workspace_id: add_link(contract_id, workspace_id, label, url), "link")


@router.post("/contracts/{contract_id}/links/{link_id}/delete")
def contract_link_remove(request: Request, contract_id: int, link_id: int, _admin: str = Depends(require_admin)):
    return _write(request, contract_id, lambda workspace_id: remove_link(contract_id, link_id, workspace_id), "link")


@router.post("/contracts/{contract_id}/links/{link_id}/move")
def contract_link_move(request: Request, contract_id: int, link_id: int, direction: str = Form(""),
                       _admin: str = Depends(require_admin)):
    return _write(request, contract_id, lambda workspace_id: move_link(contract_id, link_id, direction, workspace_id), "link")


@router.post("/contracts/{contract_id}/payments")
def contract_payment_add(
    request: Request,
    contract_id: int,
    amount_eur: str = Form(""),
    expected_on: str = Form(""),
    status: str = Form("booked"),
    _admin: str = Depends(require_admin),
):
    def add(workspace_id: int) -> None:
        try:
            amount = typed_number(amount_eur)
        except InvalidOperation:
            amount = None
        add_payment(contract_id, workspace_id, amount, parse_day(expected_on), status)
    return _write(request, contract_id, add, "payment", then=f"/contracts/{contract_id}?open=payments")
