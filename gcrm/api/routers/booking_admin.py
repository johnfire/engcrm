"""Chris's Bookings page (signed in): the list, approvals, linking, and the page's settings.

Every action redirects back to /bookings/ with a short message, so a reload never repeats a
POST. Each action stands alone: one failing (say a mail server down on approve) shows its
error and leaves everything else as it was.
"""
import logging
import re
from datetime import datetime, timedelta
from urllib.parse import urlencode, urlsplit

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from gcrm.api.auth import require_login
from gcrm.api.booking_guest_view import PREVIEW_PATH, guest_language, render_guest_page, slot_view
from gcrm.api.templates import templates
from gcrm.booking import booking_service as service
from gcrm.booking import crm_link, notifications
from gcrm.booking.booking_store import get_booking, list_bookings, purge_old_bookings
from gcrm.booking.booking_texts import LANGUAGES, has_text, text
from gcrm.booking.busy_feed import feed_link_problem
from gcrm.booking.hours_text import format_day_hours, parse_day_hours
from gcrm.booking.setup_store import (
    CUSTOM_LENGTHS,
    add_booking_block,
    add_booking_feed,
    create_booking_link,
    delete_booking_block,
    delete_booking_feed,
    ensure_booking_defaults,
    get_booking_settings,
    list_booking_feeds,
    list_booking_hours,
    list_booking_links,
    list_booking_types,
    list_upcoming_blocks,
    relabel_booking_feed,
    replace_booking_hours,
    retire_booking_link,
    update_booking_settings,
    update_booking_type,
)
from gcrm.config import APP_PUBLIC_URL
from gcrm.dates import parse_day
from gcrm.sources import MANUAL_WEB
from gcrm.tools.db_audit import log_audit
from gcrm.tools.db_people import save_person

logger = logging.getLogger(__name__)


def _defaults_exist() -> None:
    """Runs before every Bookings request, so no save can come before the settings row exists."""
    ensure_booking_defaults()


router = APIRouter(prefix="/bookings", tags=["bookings"],
                   dependencies=[Depends(require_login), Depends(_defaults_exist)])
EMAIL_OR_EMPTY = re.compile(r"^$|^[^@\s]+@[^@\s]+\.[^@\s]+$")
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,39}$")
CLOCK = re.compile(r"^(\d{1,2})[:.](\d{2})$")
BOOKING_ACTIONS = ("approve", "decline", "cancel", "held", "resend")


def _language(request: Request) -> str:
    chosen = request.session.get("ui_language")
    return chosen if chosen in LANGUAGES else "en"


def _back(message: str = "saved", error: str = "", anchor: str = "") -> RedirectResponse:
    query = urlencode({"error": error[:200]} if error else {"msg": message})
    return RedirectResponse(f"/bookings/?{query}{'#' + anchor if anchor else ''}", status_code=303)


def _page() -> service.BookingPage:
    settings_slug = get_booking_settings()["public_slug"] or ""
    return service.load_page(settings_slug)


def _error_text(language: str, error: str) -> str:
    """A refusal reason in words when it is one; anything else (a validation message) as it came."""
    return text(language, f"error.{error}") if has_text(f"error.{error}") else error


def _feed_rows() -> list[dict]:
    """Links for the page: label and host only. The full link holds the calendar's key, so it is
    never sent back to the browser."""
    return [{"id": feed["id"], "label": feed["label"],
             "host": (urlsplit(feed["url"]).hostname or "?") if feed["url"] else None}
            for feed in list_booking_feeds()]


@router.get("/", response_class=HTMLResponse)
def bookings_page(request: Request, msg: str = "", error: str = ""):
    language = _language(request)
    page = _page()
    now = service.utc_now()
    purge_old_bookings(now)
    bookings = list_bookings(now - timedelta(days=14))
    suggestions = {booking["id"]: crm_link.link_suggestions(booking) for booking in bookings
                   if booking["person_id"] is None and booking["contact_id"] is None}
    hours = {weekday: format_day_hours([(row["opens"], row["closes"]) for row in list_booking_hours()
                                        if row["weekday"] == weekday]) for weekday in range(7)}
    return templates.TemplateResponse("bookings.html", {
        "request": request, "page": page, "bookings": bookings, "suggestions": suggestions, "hours": hours,
        "all_types": {row["kind"]: row for row in list_booking_types()}, "error_text": _error_text(language, error),
        "blocks": list_upcoming_blocks(now), "links": list_booking_links(), "feeds": _feed_rows(), "now": now, "msg": msg,
        "public_url": f"{APP_PUBLIC_URL}/book/{page.slug}" if page.slug else "", "base_url": APP_PUBLIC_URL,
        "lang": language, "bt": lambda key, **values: text(language, key, **values)})


@router.get("/preview", response_class=HTMLResponse)
def preview_start(request: Request):
    """The guest's first page as a guest sees it, even while the public page is off."""
    page = _page()
    return render_guest_page(request, "booking/start.html", page, guest_language(request), base_path=PREVIEW_PATH,
                             preview=True, types=service.offered_types(page, None), link=None)


@router.get("/preview/{kind}", response_class=HTMLResponse)
def preview_times(request: Request, kind: str, week: int = 0, minutes: int | None = None):
    """Real free times from the real calendar; the book button is off."""
    page, language = _page(), guest_language(request)
    booking_type = page.types.get(kind)
    if booking_type is None:
        raise HTTPException(status_code=404, detail="Not offered.")
    if kind == "custom" and minutes not in CUSTOM_LENGTHS:
        minutes = CUSTOM_LENGTHS[0]
    view = slot_view(page, booking_type, min(max(week, 0), 52), minutes if kind == "custom" else None, language)
    return render_guest_page(request, "booking/times.html", page, language, base_path=PREVIEW_PATH, preview=True,
                             booking_type=booking_type, minutes=minutes, custom_lengths=CUSTOM_LENGTHS, link=None,
                             **view)


def _settings_from_form(form) -> dict:
    slug = form.get("public_slug", "").strip().lower()
    if slug and not SLUG.fullmatch(slug):
        raise ValueError("address: 2-40 lowercase letters, digits or dashes")
    for field in ("organizer_email", "host_email"):
        if not EMAIL_OR_EMPTY.fullmatch(form.get(field, "").strip()):
            raise ValueError(f"{field}: not an email address")
    room_link = form.get("room_link", "").strip()
    if room_link and not room_link.startswith("https://"):
        raise ValueError("room_link: must start with https://")
    changes = {"public_slug": slug or None, "is_enabled": form.get("is_enabled") == "on",
               **{field: form.get(field, "").strip() for field in ("organizer_email", "organizer_name", "host_email",
                                                                   "room_link")},
               **{field: int(form.get(field, "0")) for field in ("min_notice_hours", "horizon_days", "gap_minutes",
                                                                 "cancel_cutoff_hours")}}
    if changes["is_enabled"] and not (slug and changes["organizer_email"] and changes["host_email"]):
        raise ValueError("switch on needs an address, a sender and your calendar address")
    return changes


@router.post("/settings")
async def save_settings(request: Request):
    try:
        update_booking_settings(_settings_from_form(await request.form()))
    except Exception as error:
        logger.warning("booking settings not saved: %s", error)
        return _back(error=str(error) if isinstance(error, ValueError) else "check the values", anchor="settings")
    log_audit(None, None, "booking.settings_saved", "booking_settings", "saved")
    return _back(anchor="settings")


@router.post("/hours")
async def save_hours(request: Request):
    form = await request.form()
    try:
        week = [(weekday, opens, closes) for weekday in range(7)
                for opens, closes in parse_day_hours(form.get(f"day{weekday}", ""))]
    except ValueError as error:
        return _back(error=str(error), anchor="hours")
    replace_booking_hours(week)
    log_audit(None, None, "booking.hours_saved", "booking_hours", f"{len(week)} windows")
    return _back(anchor="hours")


@router.post("/types")
async def save_types(request: Request):
    form = await request.form()
    try:
        for kind in ("call", "video", "visit", "custom"):
            weekdays = [int(day) for day in form.getlist(f"{kind}_weekdays")]
            update_booking_type(kind, minutes=int(form.get(f"{kind}_minutes")),
                                travel_minutes=int(form.get(f"{kind}_travel", "0")), weekdays=weekdays or None,
                                is_active=form.get(f"{kind}_active") == "on")
    except Exception as error:
        logger.warning("booking types not saved: %s", error)
        return _back(error="check the minutes", anchor="types")
    log_audit(None, None, "booking.types_saved", "booking_types", "saved")
    return _back(anchor="types")


def _local_moment(day: str, clock: str, zone) -> datetime:
    match = CLOCK.fullmatch(clock.strip())
    if not match:
        raise ValueError(f"not a time: {clock!r}")
    return datetime.combine(parse_day(day), datetime.min.time(), tzinfo=zone).replace(
        hour=int(match.group(1)), minute=int(match.group(2)))


@router.post("/feeds")
def add_feed(label: str = Form(""), url: str = Form("")):
    link = url.strip()
    if label.strip() and link.startswith("https://"):  # the cheap checks below catch the rest
        problem = feed_link_problem(link)
        if problem:
            return _back(error=problem, anchor="feeds")
    try:
        feed_id = add_booking_feed(label, url)
    except ValueError as error:
        return _back(error=str(error), anchor="feeds")
    log_audit(None, None, "booking.feed_added", f"booking_feed:{feed_id}", "added")
    return _back(anchor="feeds")


@router.post("/feeds/{feed_id}/label")
def rename_feed(feed_id: int, label: str = Form("")):
    try:
        found = relabel_booking_feed(feed_id, label)
    except ValueError as error:
        return _back(error=str(error), anchor="feeds")
    if not found:
        raise HTTPException(status_code=404, detail="No such calendar link.")
    log_audit(None, None, "booking.feed_relabelled", f"booking_feed:{feed_id}", "relabelled")
    return _back(anchor="feeds")


@router.post("/feeds/{feed_id}/delete")
def remove_feed(feed_id: int):
    if not delete_booking_feed(feed_id):
        raise HTTPException(status_code=404, detail="No such calendar link.")
    log_audit(None, None, "booking.feed_removed", f"booking_feed:{feed_id}", "removed")
    return _back(anchor="feeds")


@router.post("/blocks")
def add_block(day: str = Form(...), start: str = Form(...), end: str = Form(...), note: str = Form("")):
    zone = _page().zone
    try:
        starts_at, ends_at = _local_moment(day, start, zone), _local_moment(day, end, zone)
        if ends_at <= starts_at:
            raise ValueError("the block ends before it starts")
    except ValueError as error:
        return _back(error=str(error), anchor="blocks")
    block_id = add_booking_block(starts_at, ends_at, note)
    log_audit(None, None, "booking.block_added", f"booking_block:{block_id}", "added")
    return _back(anchor="blocks")


@router.post("/blocks/{block_id}/delete")
def remove_block(block_id: int):
    delete_booking_block(block_id)
    log_audit(None, None, "booking.block_removed", f"booking_block:{block_id}", "removed")
    return _back(anchor="blocks")


@router.post("/links")
def make_link(label: str = Form(...), contact_id: int | None = Form(None), person_id: int | None = Form(None),
              deal_id: int | None = Form(None)):
    if contact_id is None and person_id is None:
        raise HTTPException(400, "Choose an organization or a person")
    create_booking_link(label or "Booking link", contact_id=contact_id, person_id=person_id, deal_id=deal_id)
    log_audit(None, None, "booking.link_created", f"person:{person_id}" if person_id else f"contact:{contact_id}",
              "created")
    return _back(anchor="links")


@router.post("/links/{link_id}/retire")
def retire_link(link_id: int):
    retire_booking_link(link_id)
    log_audit(None, None, "booking.link_retired", f"booking_link:{link_id}", "retired")
    return _back(anchor="links")


def _run_action(page: service.BookingPage, booking: dict, action: str) -> None:
    if action in ("approve", "decline"):
        service.decide(page, booking["id"], is_approved=action == "approve")
    elif action == "cancel":
        service.cancel(page, booking, service.utc_now(), by_guest=False)
    elif action == "held":
        if not crm_link.log_meeting_held(booking):
            raise service.BookingRefused("not_changeable")
        log_audit(None, None, "booking.held_logged", f"booking:{booking['id']}", "logged")
    elif notifications.send_invites(booking, page.settings, page.slug, "invite") is False:
        raise service.BookingRefused("invite_failed")


@router.post("/{booking_id}/action/{action}")
def booking_action(booking_id: int, action: str):
    booking = get_booking(booking_id)
    if booking is None or action not in BOOKING_ACTIONS:
        raise HTTPException(404, "Booking not found")
    try:
        _run_action(_page(), booking, action)
    except service.BookingRefused as refusal:
        return _back(error=refusal.reason)
    return _back()


@router.post("/{booking_id}/link")
def link_booking(booking_id: int, record: str = Form(...)):
    kind, _, record_id = record.partition(":")
    if kind not in ("person", "organization") or not record_id.isdigit():
        raise HTTPException(400, "Choose a person or organization")
    owner = {"person_id": int(record_id)} if kind == "person" else {"contact_id": int(record_id)}
    if not crm_link.link_booking(booking_id, _page().zone, **owner):
        return _back(error="not_changeable")
    log_audit(None, None, "booking.linked", f"booking:{booking_id}", record)
    return _back()


@router.post("/{booking_id}/create-person")
def create_person_from_booking(booking_id: int):
    booking = get_booking(booking_id)
    if booking is None:
        raise HTTPException(404, "Booking not found")
    person_id = save_person(booking["guest_name"], source=MANUAL_WEB, email=booking["guest_email"],
                            phone=booking["phone"], notes=f"Booked: {booking['company']}".strip(": "),
                            geocode_city=False)
    crm_link.link_booking(booking_id, _page().zone, person_id=person_id)
    log_audit(None, None, "booking.person_created", f"person:{person_id}", f"booking:{booking_id}")
    return _back()
