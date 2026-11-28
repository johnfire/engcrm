"""Booking actions, start to finish: book, confirm, move, cancel, approve or decline.

Order inside every action: validate, save the booking (the only step that can refuse),
then the CRM link and the emails, each isolated so their failure never undoes the booking.
The start time a booker sends is never trusted: it must be one of the free starts computed
now, and the database re-checks overlap under its lock.
"""
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from gcrm.booking import crm_link, notifications
from gcrm.booking.availability import available_starts
from gcrm.booking.booking_store import (
    NewBooking,
    SlotTaken,
    cancel_booking,
    confirm_hold,
    count_open_holds,
    create_booking,
    decide_request,
    get_booking,
    move_booking,
)
from gcrm.booking.setup_store import CUSTOM_LENGTHS, get_booking_settings, list_booking_types
from gcrm.booking.slots import occupied_span
from gcrm.tools.db_audit import log_audit

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAX_OPEN_HOLDS = 2
PUBLIC_ACTOR = ("public-booker", "user")


class BookingRefused(ValueError):
    """A booking cannot be made or changed; `reason` is a short key the page translates."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class BookingPage:
    slug: str
    settings: dict
    types: dict  # kind -> booking_types row
    zone: ZoneInfo


@dataclass(frozen=True)
class BookingForm:
    kind: str
    starts_at: datetime
    guest_name: str
    guest_email: str
    company: str = ""
    topic: str = ""
    visit_address: str = ""
    phone: str = ""
    language: str = "de"
    custom_minutes: int | None = None


def load_page(slug: str) -> BookingPage:
    """Settings and active types of the current workspace (call inside its scope)."""
    settings = get_booking_settings()
    types = {row["kind"]: row for row in list_booking_types() if row["is_active"]}
    return BookingPage(slug, settings, types, ZoneInfo(settings["time_zone"]))


def offered_types(page: BookingPage, link: dict | None) -> list[dict]:
    allowed = set(link["kinds"]) if link else set(page.types)
    return [row for kind, row in page.types.items() if kind in allowed]


def _minutes_for(form: BookingForm, booking_type: dict) -> int:
    if booking_type["kind"] != "custom":
        return booking_type["minutes"]
    if form.custom_minutes not in CUSTOM_LENGTHS:
        raise BookingRefused("length_needed")
    return form.custom_minutes


def _check_form(form: BookingForm, booking_type: dict) -> None:
    required = {"name_needed": form.guest_name.strip(), "email_needed": EMAIL_PATTERN.fullmatch(form.guest_email.strip()),
                "topic_needed": form.topic.strip() if booking_type["kind"] == "custom" else "x",
                "address_needed": form.visit_address.strip() if booking_type["kind"] == "visit" else "x",
                "phone_needed": form.phone.strip() if booking_type["kind"] == "call" else "x"}
    missing = next((reason for reason, value in required.items() if not value), None)
    if missing:
        raise BookingRefused(missing)


def _status_for(booking_type: dict, link: dict | None) -> str:
    if booking_type["needs_approval"]:
        return "requested"
    return "confirmed" if link else "held"


def _require_free(page: BookingPage, booking_type: dict, starts_at: datetime, minutes: int, now: datetime,
                  except_booking_id: int | None = None) -> None:
    starts = available_starts(booking_type, page.settings, now, minutes=minutes, except_booking_id=except_booking_id)
    if starts is None:
        raise BookingRefused("calendar_unavailable")
    if starts_at not in starts:
        raise BookingRefused("slot_taken")


def _after_confirmed(page: BookingPage, booking_id: int) -> None:
    crm_link.link_when_confirmed(get_booking(booking_id), page.zone)
    notifications.send_invites(get_booking(booking_id), page.settings, page.slug, "invite")


def book(page: BookingPage, form: BookingForm, link: dict | None, now: datetime) -> dict:
    booking_type = page.types.get(form.kind)
    if booking_type is None or booking_type not in offered_types(page, link):
        raise BookingRefused("type_unavailable")
    _check_form(form, booking_type)
    minutes = _minutes_for(form, booking_type)
    if link is None and count_open_holds(form.guest_email) >= MAX_OPEN_HOLDS:
        raise BookingRefused("too_many_holds")
    _require_free(page, booking_type, form.starts_at, minutes, now)
    status = _status_for(booking_type, link)
    new = NewBooking(
        booking_type_id=booking_type["id"], status=status, starts_at=form.starts_at,
        ends_at=form.starts_at + timedelta(minutes=minutes),
        occupied=occupied_span(form.starts_at, minutes, booking_type["travel_minutes"], page.settings["gap_minutes"]),
        guest_name=form.guest_name, guest_email=form.guest_email, company=form.company, topic=form.topic,
        visit_address=form.visit_address, phone=form.phone, language=form.language,
        link_id=link["id"] if link else None, contact_id=link["contact_id"] if link else None,
        person_id=link["person_id"] if link else None, deal_id=link["deal_id"] if link else None)
    try:
        created = create_booking(new)
    except SlotTaken:
        raise BookingRefused("slot_taken") from None
    log_audit(*PUBLIC_ACTOR, "booking.created", f"booking:{created.booking_id}", status)
    booking = get_booking(created.booking_id)
    if status == "held":
        notifications.send_confirm_request(booking, page.settings, page.slug, created.confirm_token)
    elif status == "requested":
        notifications.send_request_received(booking, page.settings, page.slug)
    else:
        _after_confirmed(page, created.booking_id)
    return get_booking(created.booking_id)


def confirm(page: BookingPage, confirm_token: str) -> dict | None:
    booking, was_confirmed_now = confirm_hold(confirm_token)
    if was_confirmed_now:
        log_audit(*PUBLIC_ACTOR, "booking.confirmed", f"booking:{booking['id']}", "confirmed")
        _after_confirmed(page, booking["id"])
    return get_booking(booking["id"]) if booking else None


def guest_may_change(booking: dict, page: BookingPage, now: datetime) -> bool:
    cutoff = timedelta(hours=page.settings["cancel_cutoff_hours"])
    return booking["status"] in ("confirmed", "requested") and booking["starts_at"] - now >= cutoff


def move(page: BookingPage, booking: dict, starts_at: datetime, now: datetime, by_guest: bool) -> dict:
    if by_guest and not guest_may_change(booking, page, now):
        raise BookingRefused("too_late")
    booking_type = page.types.get(booking["kind"]) or {"kind": booking["kind"], "travel_minutes": booking["travel_minutes"],
                                                       "minutes": booking["type_minutes"], "weekdays": None}
    minutes = int((booking["ends_at"] - booking["starts_at"]).total_seconds() // 60)
    _require_free(page, booking_type, starts_at, minutes, now, except_booking_id=booking["id"])
    occupied = occupied_span(starts_at, minutes, booking["travel_minutes"], page.settings["gap_minutes"])
    try:
        moved = move_booking(booking["id"], starts_at, starts_at + timedelta(minutes=minutes), occupied)
    except SlotTaken:
        raise BookingRefused("slot_taken") from None
    if moved is None:
        raise BookingRefused("not_changeable")
    log_audit(*(PUBLIC_ACTOR if by_guest else (None, None)), "booking.moved", f"booking:{booking['id']}", "moved")
    moved = get_booking(booking["id"])
    if moved["status"] == "confirmed":
        crm_link.move_follow_up(moved, page.zone)
        notifications.send_invites(moved, page.settings, page.slug, "moved")
    return moved


def cancel(page: BookingPage, booking: dict, now: datetime, by_guest: bool) -> dict:
    if by_guest and not guest_may_change(booking, page, now):
        raise BookingRefused("too_late")
    was_confirmed = booking["status"] == "confirmed"
    if cancel_booking(booking["id"]) is None:
        raise BookingRefused("not_changeable")
    log_audit(*(PUBLIC_ACTOR if by_guest else (None, None)), "booking.cancelled", f"booking:{booking['id']}",
              "by_guest" if by_guest else "by_owner")
    cancelled = get_booking(booking["id"])
    crm_link.close_follow_up(cancelled, "dismissed")
    if was_confirmed:
        notifications.send_invites(cancelled, page.settings, page.slug, "cancelled")
    return cancelled


def decide(page: BookingPage, booking_id: int, is_approved: bool) -> dict:
    if decide_request(booking_id, is_approved) is None:
        raise BookingRefused("not_changeable")
    log_audit(None, None, "booking.request_decided", f"booking:{booking_id}", "approved" if is_approved else "declined")
    if is_approved:
        _after_confirmed(page, booking_id)
    else:
        notifications.send_declined(get_booking(booking_id), page.settings, page.slug)
    return get_booking(booking_id)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
