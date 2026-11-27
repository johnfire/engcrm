"""Contracts: the deals made, grouped by when they run. Everyone signed in can look; this page changes
nothing. Every figure is worked out from the contract's payments (gcrm/contract_math.py), so it matches the
Forecast. Works inside the signed-in account's own workspace."""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse

from gcrm.api.auth import require_login
from gcrm.api.offer_filter import web_offer_filter
from gcrm.api.session_workspace import session_workspace_id
from gcrm.api.templates import templates
from gcrm.contract_kinds import CONTRACT_KINDS
from gcrm.contract_math import SECTIONS, group_by_timing, totals
from gcrm.tools.db_contracts import list_contracts
from gcrm.workspace_context import workspace_scope

router = APIRouter(tags=["contracts"], dependencies=[Depends(require_login)])


@router.get("/contracts/", response_class=HTMLResponse)
def contracts_page(
    request: Request,
    offer: Optional[str] = Query(default=None),
    kind: Optional[str] = Query(default=None),
):
    active_offer, offers = web_offer_filter(request, offer)
    kind = kind if kind in CONTRACT_KINDS else None            # an unknown kind shows every kind
    workspace_id = session_workspace_id(request)
    with workspace_scope(workspace_id):
        contracts = list_contracts(workspace_id, active_offer, kind)
    groups = group_by_timing(contracts, date.today())
    sections = [{"key": key, "contracts": groups[key], "totals": totals(groups[key])} for key in SECTIONS]
    return templates.TemplateResponse("contracts.html", {
        "request": request, "sections": sections, "totals": totals(contracts), "kinds": CONTRACT_KINDS,
        "active_kind": kind, "offers": offers, "active_offer": active_offer,
    })
