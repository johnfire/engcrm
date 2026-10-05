"""Statistics page, and recording what it counts from the web: sales and activities
on an organization, and the default minutes per activity type.
See docs/plans/2026-10-05-statistics-design.md."""
from datetime import date
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from gcrm.activity_types import ACTIVITY_TYPES, ORGANIZATION_METHODS, parse_minutes
from gcrm.api.auth import require_admin, require_login
from gcrm.api.redirects import local_redirect
from gcrm.api.templates import templates
from gcrm.db.connection import db
from gcrm.tools.db_interactions import log_meeting_note
from gcrm.tools.statistics import (
    PERIODS,
    add_sale,
    delete_sale,
    get_statistics,
    period_bounds,
    set_minute_defaults,
)

router = APIRouter(tags=["statistics"], dependencies=[Depends(require_login)])


def _workspace_id(request: Request) -> int:
    """The signed-in account's workspace; the shared admin login works in the default one."""
    workspace_id = request.session.get("workspace_id")
    if workspace_id is not None:
        return workspace_id
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM workspaces WHERE slug = 'default'")
        return cur.fetchone()["id"]


def _period(period: str, start: str, end: str, today: date) -> tuple[str, date, date]:
    if period == "custom":
        try:
            first, last = date.fromisoformat(start), date.fromisoformat(end)
        except ValueError:
            raise HTTPException(status_code=400, detail="Dates must be YYYY-MM-DD")
        if last < first or (last - first).days > 3660:
            raise HTTPException(status_code=400, detail="The end must be after the start, within ten years")
        return period, first, last
    period = period if period in PERIODS else "month"
    first, last = period_bounds(period, today)
    return period, first, last


@router.get("/statistics", response_class=HTMLResponse)
def statistics_page(
    request: Request,
    period: str = Query(default="month"),
    start: str = Query(default=""),
    end: str = Query(default=""),
    saved: bool = Query(default=False),
):
    period, first, last = _period(period, start, end, date.today())
    stats = get_statistics(_workspace_id(request), first, last)
    return templates.TemplateResponse("statistics.html", {
        "request": request, "stats": stats, "period": period, "periods": PERIODS,
        "activity_types": ACTIVITY_TYPES, "saved": saved,
    })


@router.post("/statistics/minutes")
async def save_minute_defaults(request: Request, _admin: str = Depends(require_admin)):
    form = await request.form()
    minutes = {}
    for kind in ACTIVITY_TYPES:
        try:
            value = parse_minutes(form.get(f"minutes_{kind}"))
        except ValueError:
            raise HTTPException(status_code=400, detail="Minutes must be a whole number from 0 to 1440")
        if value is not None:
            minutes[kind] = value
    set_minute_defaults(_workspace_id(request), minutes)
    return local_redirect("/statistics", saved="1")


@router.post("/organizations/{contact_id}/sales")
def record_sale(
    request: Request,
    contact_id: int,
    amount_eur: str = Form(...),
    won_on: str = Form(...),
    description: str = Form(""),
    _admin: str = Depends(require_admin),
):
    try:
        amount = Decimal(amount_eur.replace(",", ".").strip()).quantize(Decimal("0.01"))
        when = date.fromisoformat(won_on)
        sale_id = add_sale(_workspace_id(request), contact_id, amount, when, description[:500])
    except (InvalidOperation, ValueError):
        raise HTTPException(status_code=400, detail="Enter an amount above 0 and a date")
    if sale_id is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return local_redirect(f"/organizations/{contact_id}", saved="1")


@router.post("/organizations/{contact_id}/sales/{sale_id}/delete")
def remove_sale(contact_id: int, sale_id: int, _admin: str = Depends(require_admin)):
    if not delete_sale(contact_id, sale_id):
        raise HTTPException(status_code=404, detail="Sale not found")
    return local_redirect(f"/organizations/{contact_id}", saved="1")


@router.post("/organizations/{contact_id}/activity")
def log_activity(
    request: Request,
    contact_id: int,
    method: str = Form(""),
    duration_minutes: str = Form(""),
    note: str = Form(""),
    _admin: str = Depends(require_admin),
):
    """Log a drop-in, meeting, call, video call, email or plain note on an organization."""
    method = method.strip() or None
    if method is not None and method not in ORGANIZATION_METHODS:
        raise HTTPException(status_code=400, detail="Unknown activity type")
    try:
        minutes = parse_minutes(duration_minutes)
    except ValueError:
        raise HTTPException(status_code=400, detail="Minutes must be a whole number from 0 to 1440")
    if not note.strip():
        raise HTTPException(status_code=400, detail="Say what happened")
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM contacts WHERE id = %s AND workspace_id = %s AND deleted_at IS NULL",
                    (contact_id, _workspace_id(request)))
        if cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="Organization not found")
    log_meeting_note(contact_id, method, note.strip(), duration_minutes=minutes)
    return local_redirect(f"/organizations/{contact_id}", saved="1")
