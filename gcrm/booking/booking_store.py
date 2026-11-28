"""Bookings in the database: create, confirm, move, cancel, decide, link, purge.

Single writer: every write that claims time first locks the workspace's booking_settings
row, then checks for overlap, then writes. Two people taking the same slot at the same
moment are serialized here; the second gets SlotTaken. Every status change is guarded by
its current status, so a retried request changes nothing the second time.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import uuid4

from gcrm.booking.setup_store import hash_token, new_token
from gcrm.booking.slots import TimeSpan, calendar_busy_span
from gcrm.db.connection import db

HOLD_FOR = timedelta(minutes=30)
UNCONFIRMED_KEPT_FOR = timedelta(hours=24)
UNLINKED_KEPT_FOR = timedelta(days=183)
_TAKES_TIME = "(status IN ('requested','confirmed') OR (status='held' AND hold_expires_at > NOW()))"


class SlotTaken(Exception):
    """The chosen time was taken by someone else a moment ago."""


@dataclass(frozen=True)
class NewBooking:
    booking_type_id: int
    status: str  # held, requested or confirmed
    starts_at: datetime
    ends_at: datetime
    occupied: TimeSpan
    guest_name: str
    guest_email: str
    company: str = ""
    topic: str = ""
    visit_address: str = ""
    language: str = "de"
    link_id: int | None = None
    contact_id: int | None = None
    person_id: int | None = None
    deal_id: int | None = None


@dataclass(frozen=True)
class CreatedBooking:
    booking_id: int
    manage_token: str
    confirm_token: str | None


def taken_spans(window: TimeSpan, gap_minutes: int) -> list[TimeSpan]:
    """Time already spoken for in `window`: live bookings (occupied span) and manual blocks."""
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute(f"SELECT occupied_from, occupied_until FROM bookings WHERE {_TAKES_TIME} "
                       "AND occupied_until > %s AND occupied_from < %s", (window.start, window.end))
        booked = [TimeSpan(row["occupied_from"], row["occupied_until"]) for row in cursor.fetchall()]
        cursor.execute("SELECT starts_at, ends_at FROM booking_blocks WHERE ends_at > %s AND starts_at < %s",
                       (window.start, window.end))
        blocked = [calendar_busy_span(TimeSpan(row["starts_at"], row["ends_at"]), gap_minutes)
                   for row in cursor.fetchall()]
    return booked + blocked


def _claim_time(cursor, occupied: TimeSpan, except_booking_id: int | None = None) -> None:
    cursor.execute("SELECT 1 FROM booking_settings FOR UPDATE")
    cursor.execute(f"SELECT 1 FROM bookings WHERE {_TAKES_TIME} AND occupied_until > %s AND occupied_from < %s "
                   "AND id IS DISTINCT FROM %s LIMIT 1", (occupied.start, occupied.end, except_booking_id))
    if cursor.fetchone() is not None:
        raise SlotTaken()


def create_booking(new: NewBooking) -> CreatedBooking:
    manage_token, manage_hash = new_token()
    confirm_token, confirm_hash = new_token() if new.status == "held" else (None, None)
    with db() as connection:
        cursor = connection.cursor()
        _claim_time(cursor, new.occupied)
        cursor.execute(
            """INSERT INTO bookings (booking_type_id, link_id, status, starts_at, ends_at, occupied_from, occupied_until,
                   hold_expires_at, guest_name, guest_email, company, topic, visit_address, language, ics_uid,
                   confirm_token_hash, manage_token_hash, contact_id, person_id, deal_id)
               VALUES (%s,%s,%s,%s,%s,%s,%s, CASE WHEN %s='held' THEN NOW() + %s END,
                       %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (new.booking_type_id, new.link_id, new.status, new.starts_at, new.ends_at, new.occupied.start,
             new.occupied.end, new.status, HOLD_FOR, new.guest_name.strip(), new.guest_email.strip().lower(),
             new.company.strip(), new.topic.strip(), new.visit_address.strip(), new.language,
             f"{uuid4()}@engcrm-booking", confirm_hash, manage_hash, new.contact_id, new.person_id, new.deal_id))
        booking_id = cursor.fetchone()["id"]
    return CreatedBooking(booking_id, manage_token, confirm_token)


def count_open_holds(guest_email: str) -> int:
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT count(*) AS holds FROM bookings WHERE lower(guest_email)=lower(%s) "
                       "AND status='held' AND hold_expires_at > NOW()", (guest_email.strip(),))
        return cursor.fetchone()["holds"]


def confirm_hold(confirm_token: str) -> tuple[dict | None, bool]:
    """(booking, was_confirmed_now). A second click finds the booking already confirmed."""
    token_hash = hash_token(confirm_token)
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("UPDATE bookings SET status='confirmed', hold_expires_at=NULL, updated_at=NOW() "
                       "WHERE confirm_token_hash=%s AND status='held' AND hold_expires_at > NOW() RETURNING *",
                       (token_hash,))
        confirmed = cursor.fetchone()
        if confirmed is not None:
            return dict(confirmed), True
        cursor.execute("SELECT * FROM bookings WHERE confirm_token_hash=%s", (token_hash,))
        existing = cursor.fetchone()
    return (dict(existing) if existing else None), False


def booking_for_manage_token(manage_token: str) -> dict | None:
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT * FROM bookings WHERE manage_token_hash=%s", (hash_token(manage_token),))
        row = cursor.fetchone()
    return dict(row) if row else None


def get_booking(booking_id: int) -> dict | None:
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT b.*, t.kind, t.minutes AS type_minutes, t.travel_minutes FROM bookings b "
                       "JOIN booking_types t ON t.id = b.booking_type_id WHERE b.id=%s", (booking_id,))
        row = cursor.fetchone()
    return dict(row) if row else None


def move_booking(booking_id: int, starts_at: datetime, ends_at: datetime, occupied: TimeSpan) -> dict | None:
    """New times for a confirmed or requested booking; the invite sequence goes up by one."""
    with db() as connection:
        cursor = connection.cursor()
        _claim_time(cursor, occupied, except_booking_id=booking_id)
        cursor.execute("UPDATE bookings SET starts_at=%s, ends_at=%s, occupied_from=%s, occupied_until=%s, "
                       "sequence=sequence+1, invite_sent_at=NULL, updated_at=NOW() "
                       "WHERE id=%s AND status IN ('confirmed','requested') RETURNING *",
                       (starts_at, ends_at, occupied.start, occupied.end, booking_id))
        row = cursor.fetchone()
    return dict(row) if row else None


def cancel_booking(booking_id: int) -> dict | None:
    """None when it was not live (already cancelled, declined or an expired hold)."""
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("UPDATE bookings SET status='cancelled', hold_expires_at=NULL, sequence=sequence+1, "
                       f"updated_at=NOW() WHERE id=%s AND {_TAKES_TIME} RETURNING *", (booking_id,))
        row = cursor.fetchone()
    return dict(row) if row else None


def decide_request(booking_id: int, is_approved: bool) -> dict | None:
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("UPDATE bookings SET status=%s, updated_at=NOW() WHERE id=%s AND status='requested' "
                       "RETURNING *", ("confirmed" if is_approved else "declined", booking_id))
        row = cursor.fetchone()
    return dict(row) if row else None


def record_invite_result(booking_id: int, error: str) -> None:
    with db() as connection:
        connection.cursor().execute(
            "UPDATE bookings SET invite_sent_at=CASE WHEN %s='' THEN NOW() END, invite_error=%s WHERE id=%s",
            (error, error[:500], booking_id))


def list_bookings(since: datetime) -> list[dict]:
    """Bookings ending after `since` plus every live one, soonest first, with names for linked records."""
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute(
            """SELECT b.*, t.kind, c.name AS organization_name, p.name AS person_name
                 FROM bookings b JOIN booking_types t ON t.id = b.booking_type_id
                 LEFT JOIN contacts c ON c.id = b.contact_id LEFT JOIN people p ON p.id = b.person_id
                WHERE b.ends_at > %s OR b.status IN ('requested')
                ORDER BY b.starts_at""", (since,))
        return [dict(row) for row in cursor.fetchall()]


def find_person_by_email(email: str) -> dict | None:
    """The one person with this email. None when there is none, or several (Chris decides then)."""
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id, contact_id FROM people WHERE lower(email)=lower(%s) AND deleted_at IS NULL "
                       "LIMIT 2", (email.strip(),))
        matches = cursor.fetchall()
    return dict(matches[0]) if len(matches) == 1 else None


def set_booking_link(booking_id: int, *, contact_id: int | None, person_id: int | None, deal_id: int | None,
                     follow_up_id: int | None) -> None:
    with db() as connection:
        connection.cursor().execute(
            "UPDATE bookings SET contact_id=%s, person_id=%s, deal_id=%s, follow_up_id=%s, updated_at=NOW() "
            "WHERE id=%s", (contact_id, person_id, deal_id, follow_up_id, booking_id))


def purge_old_bookings(now: datetime) -> int:
    """Delete unconfirmed holds after a day and never-linked bookings half a year after they ended.
    Running it twice deletes nothing more. Returns how many rows went."""
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("DELETE FROM bookings WHERE (status='held' AND created_at < %s) "
                       "OR (contact_id IS NULL AND person_id IS NULL AND ends_at < %s AND status <> 'requested')",
                       (now - UNCONFIRMED_KEPT_FOR, now - UNLINKED_KEPT_FOR))
        return cursor.rowcount
