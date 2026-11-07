"""Forecast: what is coming in and when, by month, quarter or year, against a target.

Everyone signed in can look; only an admin changes the plan (the income needed per month,
and other income that covers part of it). Every handler works inside the signed-in
account's own workspace.
"""
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from gcrm.api.auth import require_admin, require_login
from gcrm.api.offer_filter import web_offer_filter
from gcrm.api.redirects import local_redirect
from gcrm.api.session_workspace import session_workspace_id
from gcrm.api.templates import templates
from gcrm.dates import parse_day
from gcrm.forecast_math import GRANULARITIES
from gcrm.tools.forecast import get_forecast
from gcrm.tools.income_plan import (
    add_other_income,
    delete_other_income,
    save_monthly_need,
    set_other_income_confirmed,
)
from gcrm.workspace_context import workspace_scope

router = APIRouter(tags=["forecast"], dependencies=[Depends(require_login)])


def period_label(granularity: str, start: date) -> str:
    """Month 11.2026, quarter Q4 2026, year 2026: the same in every language."""
    if granularity == "month":
        return f"{start:%m.%Y}"
    if granularity == "quarter":
        return f"Q{(start.month - 1) // 3 + 1} {start.year}"
    return str(start.year)


@router.get("/forecast", response_class=HTMLResponse)
def forecast_page(
    request: Request,
    view: str = Query(default="month"),
    offer: Optional[str] = Query(default=None),
):
    view = view if view in GRANULARITIES else "month"
    active_offer, offers = web_offer_filter(request, offer)
    workspace_id = session_workspace_id(request)
    with workspace_scope(workspace_id):
        forecast = get_forecast(workspace_id, view, date.today(), active_offer)
    labels = {p["start"]: period_label(view, p["start"]) for p in forecast["periods"]}
    tile_labels = {t["key"]: period_label(t["granularity"], t["start"]) for t in forecast["tiles"]}
    return templates.TemplateResponse("forecast.html", {
        "request": request, "forecast": forecast, "view": view, "views": GRANULARITIES, "labels": labels,
        "tile_labels": tile_labels, "offers": offers, "active_offer": active_offer, "today": date.today().isoformat(),
        "is_admin": request.session.get("role") == "admin",
    })


def _back(view: str):
    return local_redirect("/forecast", view=view if view in GRANULARITIES else "month")


@router.post("/forecast/need", dependencies=[Depends(require_admin)])
def save_need(request: Request, monthly_need: str = Form(...), view: str = Form("month")):
    """Set the income needed per month from sales."""
    try:
        amount = Decimal(monthly_need.replace(",", ".").strip())
        with workspace_scope(session_workspace_id(request)):
            save_monthly_need(amount)
    except (InvalidOperation, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error) or "Enter the amount you need per month")
    return _back(view)


@router.post("/forecast/other-income", dependencies=[Depends(require_admin)])
def add_income(
    request: Request,
    label: str = Form(...),
    amount_eur: str = Form(...),
    first_received_on: str = Form(...),
    payments: int = Form(1),
    confirmed: str = Form(""),
    view: str = Form("month"),
):
    """Add other income: an amount arriving on a day, then monthly, so many times."""
    try:
        day = parse_day(first_received_on)
        if day is None:
            raise ValueError("enter the day the first payment arrives, like 01.12.2026")
        amount = Decimal(amount_eur.replace(",", ".").strip())
        with workspace_scope(session_workspace_id(request)):
            add_other_income(label, amount, day, payments, confirmed == "1")
    except (InvalidOperation, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error) or "Check the amount and the dates")
    return _back(view)


@router.post("/forecast/other-income/{line_id}/confirmed", dependencies=[Depends(require_admin)])
def confirm_income(request: Request, line_id: int, confirmed: str = Form(""), view: str = Form("month")):
    with workspace_scope(session_workspace_id(request)):
        if not set_other_income_confirmed(line_id, confirmed == "1"):
            raise HTTPException(status_code=404, detail="Not found")
    return _back(view)


@router.post("/forecast/other-income/{line_id}/delete", dependencies=[Depends(require_admin)])
def remove_income(request: Request, line_id: int, view: str = Form("month")):
    with workspace_scope(session_workspace_id(request)):
        if not delete_other_income(line_id):
            raise HTTPException(status_code=404, detail="Not found")
    return _back(view)
