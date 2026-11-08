"""Statistics page, and recording what it counts from the web: sales and activities
on an organization, and the default minutes per activity type.
See docs/plans/2026-10-05-statistics-design.md."""
from datetime import date
from decimal import InvalidOperation

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from gcrm.activity_types import (
    ACTIVITY_TYPES,
    ATTITUDES,
    MY_READS,
    ORGANIZATION_METHODS,
    parse_choices,
    parse_minutes,
    parse_occurred_on,
)
from gcrm.api.auth import require_admin, require_login
from gcrm.api.offer_filter import web_offer_filter
from gcrm.api.redirects import local_redirect
from gcrm.api.templates import eur, templates
from gcrm.charts import bar_chart, spark
from gcrm.dates import parse_day
from gcrm.db.connection import db
from gcrm.i18n import DEFAULT_LANGUAGE, translate
from gcrm.organization_state import PIPELINE_STAGES
from gcrm.sale_series import amount_and_hours, contract_from_form, contract_hours, typed_number
from gcrm.tools.db_interactions import log_meeting_note
from gcrm.tools.deal_records import resolve_log_offer
from gcrm.tools.statistics import (
    PERIODS,
    add_sale,
    delete_sale,
    get_statistics,
    period_bounds,
    set_minute_defaults,
)
from gcrm.tools.statistics_history import BUCKETS, get_series

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
            first, last = parse_day(start, today), parse_day(end, today)
            if first is None or last is None:
                raise ValueError("both days are needed")
        except ValueError:
            raise HTTPException(status_code=400, detail="Dates must look like 28.10.2026")
        if last < first or (last - first).days > 3660:
            raise HTTPException(status_code=400, detail="The end must be after the start, within ten years")
        return period, first, last
    period = period if period in PERIODS else "month"
    first, last = period_bounds(period, today)
    return period, first, last


_BUCKET_LABEL = {"week": "%d.%m.", "month": "%m.%Y", "year": "%Y"}


def _trend_charts(series: dict, lang: str) -> dict:
    """The over-time charts: one bar chart per measure, and a small line per
    pipeline stage (each with its own scale — small multiples, not one crowded axis)."""
    fmt = _BUCKET_LABEL[series["bucket"]]
    periods = series["periods"]

    def bars(key: str, title_key: str, unit: str = "", money: bool = False) -> dict:
        def show(v):
            return f"{eur(v)}" if money else f"{v}{unit}"
        def tick(v):
            return eur(v) if money else f"{v:g}{unit}"
        points = [{"label": p["start"].strftime(fmt), "value": float(p[key]),
                   "tip": f'{p["start"].strftime(fmt)}: {show(p[key])}'} for p in periods]
        title = translate(title_key, lang)
        return {"title": title, "svg": bar_chart(points, title, tick_label=tick),
                "rows": [(pt["label"], show(p[key])) for pt, p in zip(points, periods)]}

    charts = [
        bars("hours", "statistics.chart.hours", " h"),
        bars("won_eur", "statistics.chart.won", money=True),
        bars("activities", "statistics.chart.activities"),
        bars("new_organizations", "statistics.chart.newOrganizations"),
        bars("new_people", "statistics.chart.newPeople"),
    ]
    pipeline = []
    for entity in ("organization", "person"):
        for stage in PIPELINE_STAGES:
            by_bucket = series["pipeline"].get(entity, {}).get(stage, {})
            if not by_bucket:
                continue
            ordered = sorted(by_bucket.items())
            name = f'{translate("statistics.entity." + entity, lang)} · {translate("stage." + stage, lang)}'
            points = [{"label": b.strftime(fmt), "value": n, "tip": f"{b.strftime(fmt)}: {n}"} for b, n in ordered]
            pipeline.append({"title": name, "now": ordered[-1][1], "svg": spark(points, name)})
    return {"charts": charts, "pipeline": pipeline, "logged_since": series["logged_since"]}


@router.get("/statistics", response_class=HTMLResponse)
def statistics_page(
    request: Request,
    period: str = Query(default="month"),
    start: str = Query(default=""),
    end: str = Query(default=""),
    trend: str = Query(default="month"),
    offer: str | None = Query(default=None),
    saved: bool = Query(default=False),
):
    period, first, last = _period(period, start, end, date.today())
    trend = trend if trend in BUCKETS else "month"
    workspace_id = _workspace_id(request)
    active_offer, offers = web_offer_filter(request, offer)
    stats = get_statistics(workspace_id, first, last, offer=active_offer)
    lang = request.session.get("ui_language", DEFAULT_LANGUAGE)
    trends = _trend_charts(get_series(workspace_id, trend, offer=active_offer), lang)
    return templates.TemplateResponse("statistics.html", {
        "request": request, "stats": stats, "period": period, "periods": PERIODS,
        "activity_types": ACTIVITY_TYPES, "saved": saved, "trend": trend, "trends": trends,
        "buckets": list(BUCKETS), "offers": offers, "active_offer": active_offer,
        "pipeline_stages": PIPELINE_STAGES,
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
    amount_eur: str = Form(""),
    hours: str = Form(""),
    rate: str = Form(""),
    won_on: str = Form(...),
    description: str = Form(""),
    deal_id: int | None = Form(None),
    status: str = Form("collected"),
    expected_on: str = Form(""),
    schedule: str = Form(""),
    months: int = Form(1),
    _admin: str = Depends(require_admin),
):
    """Record a sale for one of the organization's deals (Consulting's when the form names
    none), booked, contracted or already collected. `schedule` is "one" (a single payment) or
    "monthly" (the amount is per month, for `months` months, the first due on the expected day)."""
    try:
        amount, worked = amount_and_hours(typed_number(amount_eur), typed_number(hours), typed_number(rate))      # per month for a monthly schedule
        amount, months_paid = contract_from_form(amount, schedule, months)
        worked, months = contract_hours(worked, schedule, months_paid), months_paid
        when = parse_day(won_on)
        if when is None:
            raise ValueError("a sale needs its day")
        sale_id = add_sale(_workspace_id(request), contact_id, amount, when, description[:500], deal_id,
                           status=status, expected_on=parse_day(expected_on), months=months, hours=worked)
    except InvalidOperation:
        raise HTTPException(status_code=400, detail="Enter an amount above 0 and a date")
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error) or "Enter an amount above 0 and a date")
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
    offer: str | None = Form(None),
    occurred_on: str = Form(""),
    attitude: list[str] = Form([]),
    my_read: list[str] = Form([]),
    materials_left: str = Form(""),
    followup_promised: str = Form(""),
    followup_date: str = Form(""),
    _admin: str = Depends(require_admin),
):
    """Log a drop-in, meeting, call, video call, email or plain note on an
    organization: when it happened, how long it took, how it felt, what was left
    behind, any follow-up promised, and which offer it was about (0: general;
    absent: picked from the open deals)."""
    method = method.strip() or None
    if method is not None and method not in ORGANIZATION_METHODS:
        raise HTTPException(status_code=400, detail="Unknown activity type")
    try:
        minutes = parse_minutes(duration_minutes)
    except ValueError:
        raise HTTPException(status_code=400, detail="Minutes must be a whole number from 0 to 1440")
    try:
        day = parse_occurred_on(occurred_on)
    except ValueError:
        raise HTTPException(status_code=400, detail="The date must look like 28.10.2026 and be today or earlier")
    try:
        attitudes, reads = parse_choices(attitude, ATTITUDES), parse_choices(my_read, MY_READS)
    except ValueError:
        raise HTTPException(status_code=400, detail="Unknown attitude or read")
    try:
        follow_up_day = parse_day(followup_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Follow-up date must look like 28.10.2026")
    if not note.strip():
        raise HTTPException(status_code=400, detail="Say what happened")
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM contacts WHERE id = %s AND workspace_id = %s AND deleted_at IS NULL",
                    (contact_id, _workspace_id(request)))
        if cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="Organization not found")
    try:
        offer_id = resolve_log_offer("organization", contact_id, offer, _workspace_id(request))
    except ValueError:
        raise HTTPException(status_code=400, detail="Unknown offer")
    log_meeting_note(contact_id, method, note.strip(), follow_up_date=follow_up_day,
                     follow_up_text=followup_promised.strip() or None, duration_minutes=minutes,
                     offer_id=offer_id, occurred_on=day, attitude=attitudes, my_read=reads,
                     materials_left=materials_left.strip() or None)
    return local_redirect(f"/organizations/{contact_id}", saved="1")
