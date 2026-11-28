"""Public booking pages: no login. /book/<slug> for anyone; ?link=<token> for personal links.

Every request first turns the slug into its workspace (only enabled pages), then works
inside that workspace's scope, under the same row security as a signed-in user.
The confirm link shows a page with a button: mail scanners open links in emails, so a
plain GET must never confirm anything.
"""
import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, Response

from gcrm.api.rate_limit import FixedWindowRateLimiter, client_key
from gcrm.api.templates import templates
from gcrm.booking import booking_service as service
from gcrm.booking.availability import available_starts
from gcrm.booking.booking_store import booking_for_manage_token, get_booking, purge_old_bookings
from gcrm.booking.booking_texts import LANGUAGES, WEEKDAYS, describe_time, text
from gcrm.booking.notifications import invite_ics
from gcrm.booking.setup_store import CUSTOM_LENGTHS, booking_link_for_token, workspace_for_slug
from gcrm.workspace_context import workspace_scope

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/book", tags=["booking"])

_page_limiter = FixedWindowRateLimiter(max_attempts=120, window_seconds=60.0)
_write_limiter = FixedWindowRateLimiter(max_attempts=10, window_seconds=3600.0)
_email_limiter = FixedWindowRateLimiter(max_attempts=5, window_seconds=3600.0)
DAYS_PER_PAGE = 7


def booking_language(request: Request) -> str:
    chosen = request.query_params.get("lang") or request.session.get("ui_language")
    if chosen in LANGUAGES:
        return chosen
    accepted = request.headers.get("accept-language", "").lower()
    return "en" if accepted.startswith("en") else "de"


def _limit(limiter: FixedWindowRateLimiter, key: str) -> None:
    if not limiter.allow(key):
        raise HTTPException(status_code=429, detail="Too many requests; please try again later.")


def _workspace(slug: str, request: Request) -> int:
    _limit(_page_limiter, client_key(request))
    workspace_id = workspace_for_slug(slug)
    if workspace_id is None:
        raise HTTPException(status_code=404, detail="No booking page here.")
    return workspace_id


def _render(request: Request, template: str, page: service.BookingPage, language: str, **values) -> HTMLResponse:
    def words(key: str, **extra) -> str:
        return text(language, key, **extra)

    context = {"request": request, "page": page, "lang": language, "bt": words, **values}
    return templates.TemplateResponse(template, context, status_code=values.get("status_code", 200))


def _link(page_token: str | None) -> dict | None:
    return booking_link_for_token(page_token) if page_token else None


def _days_with_starts(starts: list[datetime], zone: ZoneInfo, first: date, language: str) -> list[dict]:
    days = {first + timedelta(days=offset): [] for offset in range(DAYS_PER_PAGE)}
    for start in starts:
        local = start.astimezone(zone)
        if local.date() in days:
            days[local.date()].append({"value": start.isoformat(), "label": local.strftime("%H:%M")})
    return [{"label": f"{WEEKDAYS[language][day.weekday()]}, {day.strftime('%d.%m.%Y')}", "starts": starts_of_day}
            for day, starts_of_day in days.items() if starts_of_day]


def _slot_view(page: service.BookingPage, booking_type: dict, week: int, minutes: int | None, language: str,
               except_booking_id: int | None = None) -> dict:
    now = service.utc_now()
    starts = available_starts(booking_type, page.settings, now, minutes=minutes, except_booking_id=except_booking_id)
    first = now.astimezone(page.zone).date() + timedelta(days=DAYS_PER_PAGE * week)
    weeks = max(1, -(-page.settings["horizon_days"] // DAYS_PER_PAGE))
    return {"calendar_unavailable": starts is None, "week": week, "weeks": weeks,
            "days": _days_with_starts(starts or [], page.zone, first, language)}


@router.get("/{slug}", response_class=HTMLResponse)
def booking_start(request: Request, slug: str, link: str | None = None):
    language = booking_language(request)
    with workspace_scope(_workspace(slug, request)):
        page = service.load_page(slug)
        personal = _link(link)
        return _render(request, "booking/start.html", page, language,
                       types=service.offered_types(page, personal), link=link if personal else None)


@router.get("/{slug}/{kind}", response_class=HTMLResponse)
def booking_times(request: Request, slug: str, kind: str, link: str | None = None, week: int = 0,
                  minutes: int | None = None):
    language = booking_language(request)
    with workspace_scope(_workspace(slug, request)):
        page = service.load_page(slug)
        personal = _link(link)
        booking_type = next((row for row in service.offered_types(page, personal) if row["kind"] == kind), None)
        if booking_type is None:
            raise HTTPException(status_code=404, detail="Not offered.")
        if kind == "custom" and minutes not in CUSTOM_LENGTHS:
            minutes = CUSTOM_LENGTHS[0]
        view = _slot_view(page, booking_type, min(max(week, 0), 52), minutes if kind == "custom" else None, language)
        return _render(request, "booking/times.html", page, language, booking_type=booking_type, minutes=minutes,
                       custom_lengths=CUSTOM_LENGTHS, link=link if personal else None, **view)


def _parse_start(value: str) -> datetime:
    try:
        start = datetime.fromisoformat(value)
    except ValueError:
        raise service.BookingRefused("slot_taken") from None
    if start.tzinfo is None:
        raise service.BookingRefused("slot_taken")
    return start


@router.post("/{slug}/{kind}", response_class=HTMLResponse)
def booking_submit(request: Request, slug: str, kind: str, start: str = Form(""), guest_name: str = Form(""),
                   guest_email: str = Form(""), company: str = Form(""), topic: str = Form(""),
                   visit_address: str = Form(""), phone: str = Form(""), minutes: int | None = Form(None),
                   link: str = Form(""), website: str = Form("")):
    language = booking_language(request)
    with workspace_scope(_workspace(slug, request)):
        page = service.load_page(slug)
        if website:  # honeypot: people never see this field
            return _render(request, "booking/done.html", page, language, outcome="held", email=guest_email)
        _limit(_write_limiter, client_key(request))
        _limit(_email_limiter, guest_email.strip().lower())
        try:
            form = service.BookingForm(kind=kind, starts_at=_parse_start(start), guest_name=guest_name[:200],
                                       guest_email=guest_email[:254], company=company[:200], topic=topic[:2000],
                                       visit_address=visit_address[:500], phone=phone[:40], language=language,
                                       custom_minutes=minutes)
            purge_old_bookings(service.utc_now())
            booking = service.book(page, form, _link(link), service.utc_now())
        except service.BookingRefused as refusal:
            return _render(request, "booking/problem.html", page, language, reason=refusal.reason, kind=kind,
                           link=link or None, status_code=409)
        return _render(request, "booking/done.html", page, language, outcome=booking["status"],
                       email=booking["guest_email"])


@router.get("/{slug}/confirm/{token}", response_class=HTMLResponse)
def confirm_page(request: Request, slug: str, token: str):
    language = booking_language(request)
    with workspace_scope(_workspace(slug, request)):
        return _render(request, "booking/confirm.html", service.load_page(slug), language, token=token)


@router.post("/{slug}/confirm/{token}", response_class=HTMLResponse)
def confirm_submit(request: Request, slug: str, token: str):
    language = booking_language(request)
    with workspace_scope(_workspace(slug, request)):
        page = service.load_page(slug)
        booking = service.confirm(page, token)
        outcome = booking["status"] if booking else "unknown"
        return _render(request, "booking/done.html", page, language, outcome="confirmed" if outcome == "confirmed"
                       else "expired", email=booking["guest_email"] if booking else "")


def _managed_booking(token: str) -> dict:
    found = booking_for_manage_token(token)
    if found is None:
        raise HTTPException(status_code=404, detail="Booking not found.")
    return get_booking(found["id"])


@router.get("/{slug}/manage/{token}", response_class=HTMLResponse)
def manage_page(request: Request, slug: str, token: str, week: int = 0):
    language = booking_language(request)
    with workspace_scope(_workspace(slug, request)):
        page = service.load_page(slug)
        booking = _managed_booking(token)
        may_change = service.guest_may_change(booking, page, service.utc_now())
        view = {}
        if may_change:
            booking_type = page.types.get(booking["kind"])
            minutes = int((booking["ends_at"] - booking["starts_at"]).total_seconds() // 60)
            if booking_type is not None:
                view = _slot_view(page, booking_type, min(max(week, 0), 52), minutes, language,
                                  except_booking_id=booking["id"])
        when = describe_time(language, booking["starts_at"], booking["ends_at"], page.zone)
        return _render(request, "booking/manage.html", page, language, booking=booking, token=token, when=when,
                       may_change=may_change, **view)


@router.post("/{slug}/manage/{token}/cancel", response_class=HTMLResponse)
def manage_cancel(request: Request, slug: str, token: str):
    language = booking_language(request)
    with workspace_scope(_workspace(slug, request)):
        page = service.load_page(slug)
        try:
            service.cancel(page, _managed_booking(token), service.utc_now(), by_guest=True)
        except service.BookingRefused as refusal:
            return _render(request, "booking/problem.html", page, language, reason=refusal.reason, kind=None,
                           link=None, status_code=409)
        return _render(request, "booking/done.html", page, language, outcome="cancelled", email="")


@router.post("/{slug}/manage/{token}/move", response_class=HTMLResponse)
def manage_move(request: Request, slug: str, token: str, start: str = Form("")):
    language = booking_language(request)
    with workspace_scope(_workspace(slug, request)):
        page = service.load_page(slug)
        _limit(_write_limiter, client_key(request))
        try:
            moved = service.move(page, _managed_booking(token), _parse_start(start), service.utc_now(), by_guest=True)
        except service.BookingRefused as refusal:
            return _render(request, "booking/problem.html", page, language, reason=refusal.reason, kind=None,
                           link=None, status_code=409)
        return _render(request, "booking/done.html", page, language, outcome="moved", email=moved["guest_email"])


@router.get("/{slug}/manage/{token}/invite.ics")
def manage_invite(request: Request, slug: str, token: str):
    with workspace_scope(_workspace(slug, request)):
        page = service.load_page(slug)
        booking = _managed_booking(token)
        if booking["status"] != "confirmed":
            raise HTTPException(status_code=404, detail="No invite for this booking.")
        ics = invite_ics(booking, page.settings, slug)
    return Response(ics, media_type="text/calendar; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="invite.ics"'})
