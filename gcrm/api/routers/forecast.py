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
from gcrm.api.templates import eur, templates
from gcrm.dates import parse_day
from gcrm.flow_charts import build_flow_charts
from gcrm.flow_math import DEFAULT_FLOW, FLOW_RANGES
from gcrm.forecast_math import GRANULARITIES
from gcrm.i18n import DEFAULT_LANGUAGE
from gcrm.tools.contract_flow import get_contract_flow
from gcrm.tools.forecast import get_forecast
from gcrm.tools.income_plan import (
    add_other_income,
    delete_other_income,
    save_expected_new_sales,
    save_monthly_need,
    set_other_income_confirmed,
    update_other_income,
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
    flow: str = Query(default=DEFAULT_FLOW),
    offer: Optional[str] = Query(default=None),
):
    view = view if view in GRANULARITIES else "month"
    flow = flow if flow in FLOW_RANGES else DEFAULT_FLOW
    active_offer, offers = web_offer_filter(request, offer)
    workspace_id = session_workspace_id(request)
    with workspace_scope(workspace_id):
        forecast = get_forecast(workspace_id, view, date.today(), active_offer)
        contract_flow = get_contract_flow(workspace_id, flow, date.today(), active_offer)
    lang = request.session.get("ui_language", DEFAULT_LANGUAGE)
    flow_charts = build_flow_charts(contract_flow, lang, eur)
    flow_has_data = any(b["cumulative"] for b in contract_flow["buckets"])
    labels = {p["start"]: period_label(view, p["start"]) for p in forecast["periods"]}
    tile_labels = {t["key"]: period_label(t["granularity"], t["start"]) for t in forecast["tiles"]}
    return templates.TemplateResponse("forecast.html", {
        "request": request, "forecast": forecast, "view": view, "views": GRANULARITIES, "labels": labels,
        "flow": flow, "flow_ranges": FLOW_RANGES, "flow_charts": flow_charts, "flow_has_data": flow_has_data,
        "tile_labels": tile_labels, "offers": offers, "active_offer": active_offer, "today": date.today().isoformat(),
        "is_admin": request.session.get("role") == "admin",
    })


def _back(view: str):
    return local_redirect("/forecast", view=view if view in GRANULARITIES else "month")


@router.post("/forecast/need", dependencies=[Depends(require_admin)])
def save_need(request: Request, monthly_need: str = Form(...), start_month: str = Form(""),
              view: str = Form("month")):
    """Set the income needed per month from sales, and the first month it applies to (blank:
    every month)."""
    try:
        amount = Decimal(monthly_need.replace(",", ".").strip())
        first = parse_day(start_month) if start_month.strip() else None
        if start_month.strip() and first is None:
            raise ValueError("enter the first month like 01.10.2026")
        with workspace_scope(session_workspace_id(request)):
            save_monthly_need(amount, first)
    except (InvalidOperation, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error) or "Enter the amount you need per month")
    return _back(view)


def _paying_months(typed: str) -> int | None:
    """Months each booking pays: blank is 1, a whole number is that many, "i" or "∞" is for ever (None)."""
    text = typed.strip().lower()
    if not text:
        return 1
    if text in ("i", "\u221e"):
        return None
    if not text.isdigit():
        raise ValueError("enter a whole number of months, or i for no end")
    return int(text)


@router.post("/forecast/new-sales", dependencies=[Depends(require_admin)])
def save_new_sales(request: Request, expected_new_monthly: str = Form(""), new_sales_months: str = Form(""),
                   view: str = Form("month")):
    """Set the euros of new sales expected to be booked each month (blank: no assumption) and for how
    many months each booking keeps paying (blank: 1, a one-off; "i" or "∞": for ever). Only the
    Outlook chart draws it, so the page comes back on the Outlook."""
    try:
        text = expected_new_monthly.replace(",", ".").strip()
        with workspace_scope(session_workspace_id(request)):
            save_expected_new_sales(Decimal(text) if text else None, _paying_months(new_sales_months))
    except (InvalidOperation, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error) or "Enter an amount of 0 or more")
    return local_redirect("/forecast", view=view if view in GRANULARITIES else "month", flow="outlook")


def _income_fields(label: str, amount_eur: str, first_received_on: str, covers_from: str):
    """(label, amount, first payment day, first covered month or None) from an income form."""
    day = parse_day(first_received_on)
    if day is None:
        raise ValueError("enter the day the first payment arrives, like 01.12.2026")
    covers = parse_day(covers_from) if covers_from.strip() else None
    if covers_from.strip() and covers is None:
        raise ValueError("enter the first month it covers, like 01.10.2026")
    return label, Decimal(amount_eur.replace(",", ".").strip()), day, covers


@router.post("/forecast/other-income", dependencies=[Depends(require_admin)])
def add_income(
    request: Request,
    label: str = Form(""),
    amount_eur: str = Form(...),
    first_received_on: str = Form(...),
    covers_from: str = Form(""),
    payments: int = Form(1),
    confirmed: str = Form(""),
    view: str = Form("month"),
):
    """Add other income: an amount a month, so many months, the first paid on a day and covering
    the months from `covers_from` (blank: the month of the first payment)."""
    try:
        name, amount, day, covers = _income_fields(label, amount_eur, first_received_on, covers_from)
        with workspace_scope(session_workspace_id(request)):
            add_other_income(name, amount, day, payments, confirmed == "1", covers)
    except (InvalidOperation, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error) or "Check the amount and the dates")
    return _back(view)


@router.post("/forecast/other-income/{line_id}/edit", dependencies=[Depends(require_admin)])
def edit_income(
    request: Request,
    line_id: int,
    label: str = Form(""),
    amount_eur: str = Form(...),
    first_received_on: str = Form(...),
    covers_from: str = Form(""),
    payments: int = Form(1),
    confirmed: str = Form(""),
    view: str = Form("month"),
):
    """Change a line of other income."""
    try:
        name, amount, day, covers = _income_fields(label, amount_eur, first_received_on, covers_from)
        with workspace_scope(session_workspace_id(request)):
            changed = update_other_income(line_id, name, amount, day, payments, confirmed == "1", covers)
    except (InvalidOperation, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error) or "Check the amount and the dates")
    if not changed:
        raise HTTPException(status_code=404, detail="Not found")
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
