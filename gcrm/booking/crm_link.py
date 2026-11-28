"""A booking in the CRM: a commitment follow-up while it is coming up, an activity once it
took place. Nothing here creates organizations or people: a public booker is linked only
on an exact, single email match, or by Chris by hand.

Each function is idempotent (a linked booking is not linked twice) and is called after the
booking itself is saved, so a CRM failure never loses a booking.
"""
import logging
from zoneinfo import ZoneInfo

from gcrm.booking.booking_store import (
    claim_activity_log,
    deal_owner,
    find_person_by_email,
    get_booking,
    set_booking_link,
)
from gcrm.booking.booking_texts import text
from gcrm.db.connection import db
from gcrm.tools.db_interactions import log_meeting_note
from gcrm.tools.db_people_interactions import log_person_note
from gcrm.tools.follow_ups import change_follow_up_status, create_follow_up, update_follow_up

logger = logging.getLogger(__name__)
# A shared mail provider says nothing about the employer, so its domain is never matched.
FREEMAIL_DOMAINS = frozenset({"gmail.com", "googlemail.com", "gmx.de", "gmx.net", "web.de", "t-online.de",
                              "outlook.com", "outlook.de", "hotmail.com", "hotmail.de", "live.com", "yahoo.com",
                              "yahoo.de", "icloud.com", "me.com", "proton.me", "protonmail.com", "pm.me",
                              "posteo.de", "mailbox.org", "freenet.de", "aol.com"})
# Booking kind -> (organization activity method, person activity method).
ACTIVITY_METHODS = {"call": ("phone", "call"), "video": ("video", "video"), "visit": ("meeting", "meeting"),
                    "custom": ("video", "video")}


def follow_up_text(booking: dict, zone: ZoneInfo) -> str:
    start = booking["starts_at"].astimezone(zone)
    kind = text(booking["language"], f"kind.{booking['kind']}")
    return f"{kind} {start.strftime('%d.%m.%Y %H:%M')} – {booking['guest_name']} (booked)"


def _follow_up_version(follow_up_id: int):
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT updated_at FROM follow_ups WHERE id=%s AND status='active'", (follow_up_id,))
        row = cursor.fetchone()
    return row["updated_at"] if row else None


def _owner(contact_id, person_id, deal_id) -> dict:
    if deal_id is not None:
        return {"deal_id": deal_id}
    return {"person_id": person_id} if person_id is not None else {"contact_id": contact_id}


def link_booking(booking_id: int, zone: ZoneInfo, *, contact_id: int | None = None, person_id: int | None = None,
                 deal_id: int | None = None) -> bool:
    """Tie the booking to a record and give it a commitment follow-up dated on the meeting."""
    booking = get_booking(booking_id)
    if booking is None or booking["follow_up_id"] is not None:
        return False
    if deal_id is not None:
        owner = deal_owner(deal_id)
        if owner is None:
            return False
        contact_id, person_id = owner["contact_id"], owner["person_id"]
    if contact_id is None and person_id is None:
        return False
    follow_up_id = create_follow_up(task_type="commitment", task_text=follow_up_text(booking, zone),
                                    due_date=booking["starts_at"].astimezone(zone).date(),
                                    **_owner(contact_id, person_id, deal_id))
    set_booking_link(booking_id, contact_id=contact_id, person_id=person_id, deal_id=deal_id,
                     follow_up_id=follow_up_id)
    return True


def link_when_confirmed(booking: dict, zone: ZoneInfo) -> bool:
    """On confirmation: the personal link's record, else the one person with this email."""
    try:
        if booking["contact_id"] or booking["person_id"] or booking["deal_id"]:
            return link_booking(booking["id"], zone, contact_id=booking["contact_id"],
                                person_id=booking["person_id"], deal_id=booking["deal_id"])
        match = find_person_by_email(booking["guest_email"])
        if match is None:
            return False
        return link_booking(booking["id"], zone, person_id=match["id"])
    except Exception:
        logger.exception("booking %s: linking to the CRM failed", booking["id"])
        return False


def move_follow_up(booking: dict, zone: ZoneInfo) -> None:
    version = _follow_up_version(booking["follow_up_id"]) if booking["follow_up_id"] else None
    if version is None:
        return
    try:
        update_follow_up(booking["follow_up_id"], task_type="commitment", task_text=follow_up_text(booking, zone),
                         due_date=booking["starts_at"].astimezone(zone).date(), version=version)
    except Exception:
        logger.exception("booking %s: moving its follow-up failed", booking["id"])


def close_follow_up(booking: dict, status: str) -> None:
    """completed after the meeting, dismissed when it was cancelled."""
    version = _follow_up_version(booking["follow_up_id"]) if booking["follow_up_id"] else None
    if version is None:
        return
    try:
        change_follow_up_status(booking["follow_up_id"], status, version)
    except Exception:
        logger.exception("booking %s: closing its follow-up failed", booking["id"])


def log_meeting_held(booking: dict) -> bool:
    """Record the meeting as an activity on its record (minutes = booked length) and complete
    the follow-up. False when the booking is not linked, not confirmed, or already logged."""
    if booking["contact_id"] is None and booking["person_id"] is None:
        return False
    if not claim_activity_log(booking["id"]):
        return False
    minutes = int((booking["ends_at"] - booking["starts_at"]).total_seconds() // 60)
    organization_method, person_method = ACTIVITY_METHODS[booking["kind"]]
    note = text(booking["language"], f"kind.{booking['kind']}") + (f": {booking['topic']}" if booking["topic"] else "")
    if booking["contact_id"] is not None:
        log_meeting_note(booking["contact_id"], organization_method, note, duration_minutes=minutes,
                         occurred_on=booking["starts_at"].date())
    else:
        log_person_note(booking["person_id"], person_method, note, duration_minutes=minutes)
    close_follow_up(booking, "completed")
    return True


def link_suggestions(booking: dict) -> list[dict]:
    """People and organizations that might be this booker: same email domain, same surname,
    or a company name match. At most eight; Chris picks, nothing is linked automatically."""
    domain = booking["guest_email"].rpartition("@")[2].lower()
    domain = "" if domain in FREEMAIL_DOMAINS else domain
    surname = booking["guest_name"].split()[-1] if booking["guest_name"].split() else ""
    company = booking["company"].strip()
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute(
            """SELECT 'person' AS kind, id, name FROM people WHERE deleted_at IS NULL
                  AND (lower(email) LIKE '%%@' || lower(%s) OR (length(%s) > 2 AND name ILIKE '%%' || %s || '%%'))
               UNION ALL
               SELECT 'organization', id, name FROM contacts WHERE deleted_at IS NULL
                  AND length(%s) > 2 AND name ILIKE '%%' || %s || '%%'
               LIMIT 8""", (domain, surname, surname, company, company))
        return [dict(row) for row in cursor.fetchall()]
