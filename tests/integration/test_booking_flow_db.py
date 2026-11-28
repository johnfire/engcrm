"""Booking flows on real PostgreSQL, with outgoing mail captured instead of sent."""
import email
from datetime import datetime, timedelta, timezone

import icalendar
import pytest

from gcrm.booking import booking_service as service
from gcrm.booking.availability import FEED_CACHE
from gcrm.booking.booking_service import BookingForm, BookingRefused
from gcrm.booking.booking_store import get_booking
from gcrm.booking.crm_link import log_meeting_held
from gcrm.booking.setup_store import (
    booking_link_for_token,
    create_booking_link,
    ensure_booking_defaults,
    update_booking_settings,
)
from gcrm.db.connection import db
from gcrm.workspace_context import workspace_scope

pytestmark = pytest.mark.integration

NOW = datetime(2027, 3, 1, 8, tzinfo=timezone.utc)          # Monday
WEDNESDAY_0930 = datetime(2027, 3, 3, 8, 30, tzinfo=timezone.utc)  # 09:30 Berlin


@pytest.fixture
def outbox(monkeypatch):
    sent = []
    monkeypatch.setattr("gcrm.booking.notifications.send_prepared_email",
                        lambda message, recipient: sent.append((recipient, message)) or True)
    return sent


@pytest.fixture
def page(clean_database, outbox):
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug='default'")
        workspace_id = cursor.fetchone()["id"]
    with workspace_scope(workspace_id):
        ensure_booking_defaults()
        update_booking_settings({"public_slug": "chris", "is_enabled": True, "organizer_email": "termine@example.org",
                                 "organizer_name": "Chris Example", "host_email": "host@example.net",
                                 "room_link": "https://meet.example/room"})
        yield service.load_page("chris")


def form(**changes) -> BookingForm:
    fields = dict(kind="video", starts_at=WEDNESDAY_0930, guest_name="Erika Musterfrau",
                  guest_email="erika@example.com", company="Beispiel GmbH")
    fields.update(changes)
    return BookingForm(**fields)


def calendar_method(message) -> tuple[str, int]:
    parsed = email.message_from_string(message.as_string())
    calendar_part = next(part for part in parsed.walk() if part.get_content_type() == "text/calendar")
    event = next(component for component in icalendar.Calendar.from_ical(calendar_part.get_payload(decode=True)).walk()
                 if component.name == "VEVENT")
    return calendar_part.get_param("method"), int(event["SEQUENCE"])


def add_person(name="Erika Musterfrau", email_address="erika@example.com") -> int:
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("INSERT INTO people (name, email) VALUES (%s, %s) RETURNING id", (name, email_address))
        return cursor.fetchone()["id"]


def confirm_token_from(outbox) -> str:
    body = email.message_from_string(outbox[-1][1].as_string()).get_payload()[0].get_payload(decode=True).decode()
    return body.split("/confirm/")[1].split()[0]


def test_public_booking_holds_then_confirm_sends_both_invites_and_links_by_email(page, outbox):
    person_id = add_person()
    held = service.book(page, form(), link=None, now=NOW)
    assert held["status"] == "held"
    assert [recipient for recipient, _ in outbox] == ["erika@example.com"]
    confirmed = service.confirm(page, confirm_token_from(outbox))
    assert confirmed["status"] == "confirmed"
    assert confirmed["person_id"] == person_id and confirmed["follow_up_id"] is not None
    invites = outbox[1:]
    assert sorted(recipient for recipient, _ in invites) == ["erika@example.com", "host@example.net"]
    assert all(calendar_method(message) == ("REQUEST", 0) for _, message in invites)
    assert get_booking(confirmed["id"])["invite_sent_at"] is not None


def test_clicking_confirm_again_sends_nothing_more(page, outbox):
    service.book(page, form(), link=None, now=NOW)
    token = confirm_token_from(outbox)
    service.confirm(page, token)
    count = len(outbox)
    assert service.confirm(page, token)["status"] == "confirmed"
    assert len(outbox) == count


def test_unknown_public_booker_stays_unlinked(page, outbox):
    service.book(page, form(), link=None, now=NOW)
    confirmed = service.confirm(page, confirm_token_from(outbox))
    assert confirmed["person_id"] is None and confirmed["follow_up_id"] is None


def test_personal_link_books_at_once_and_links_its_person(page, outbox):
    person_id = add_person("Max Beispiel", "max@example.com")
    token = create_booking_link("Max", contact_id=None, person_id=person_id, deal_id=None)
    booking = service.book(page, form(guest_email="max@example.com"), link=booking_link_for_token(token), now=NOW)
    assert booking["status"] == "confirmed" and booking["person_id"] == person_id
    assert booking["follow_up_id"] is not None
    assert len(outbox) == 2


def test_custom_request_waits_for_approval_then_invites(page, outbox):
    booking = service.book(page, form(kind="custom", custom_minutes=90, topic="AI in quality control"),
                           link=None, now=NOW)
    assert booking["status"] == "requested"
    assert booking["ends_at"] - booking["starts_at"] == timedelta(minutes=90)
    assert sorted(recipient for recipient, _ in outbox) == ["erika@example.com", "host@example.net"]
    approved = service.decide(page, booking["id"], is_approved=True)
    assert approved["status"] == "confirmed"
    assert sum(1 for _, message in outbox[2:] if calendar_method(message)[0] == "REQUEST") == 2


def test_required_fields_per_kind(page):
    with pytest.raises(BookingRefused, match="topic_needed"):
        service.book(page, form(kind="custom", custom_minutes=60), link=None, now=NOW)
    with pytest.raises(BookingRefused, match="length_needed"):
        service.book(page, form(kind="custom", custom_minutes=45, topic="x"), link=None, now=NOW)
    with pytest.raises(BookingRefused, match="address_needed"):
        service.book(page, form(kind="visit"), link=None, now=NOW)
    with pytest.raises(BookingRefused, match="phone_needed"):
        service.book(page, form(kind="call"), link=None, now=NOW)
    with pytest.raises(BookingRefused, match="email_needed"):
        service.book(page, form(guest_email="not-an-email"), link=None, now=NOW)


def test_a_start_time_that_is_not_offered_is_refused(page):
    with pytest.raises(BookingRefused, match="slot_taken"):
        service.book(page, form(starts_at=WEDNESDAY_0930 + timedelta(minutes=7)), link=None, now=NOW)
    with pytest.raises(BookingRefused, match="slot_taken"):
        service.book(page, form(starts_at=NOW + timedelta(hours=2)), link=None, now=NOW)  # inside 24 h notice


def test_two_open_holds_per_email_at_most(page):
    service.book(page, form(), link=None, now=NOW)
    service.book(page, form(starts_at=WEDNESDAY_0930 + timedelta(hours=5)), link=None, now=NOW)
    with pytest.raises(BookingRefused, match="too_many_holds"):
        service.book(page, form(starts_at=WEDNESDAY_0930 + timedelta(days=1)), link=None, now=NOW)


def test_unreadable_calendar_feed_closes_the_page(page, monkeypatch):
    update_booking_settings({"feed_url": "https://calendar.example/feed.ics"})
    monkeypatch.setattr(FEED_CACHE, "feed_text", lambda url: None)
    page = service.load_page("chris")
    with pytest.raises(BookingRefused, match="calendar_unavailable"):
        service.book(page, form(), link=None, now=NOW)


def test_calendar_busy_time_hides_the_slot(page, monkeypatch):
    feed = ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//x//x//EN\r\nBEGIN:VEVENT\r\nUID:a\r\nDTSTAMP:20270101T000000Z\r\n"
            "DTSTART:20270303T090000Z\r\nDTEND:20270303T100000Z\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n")
    update_booking_settings({"feed_url": "https://calendar.example/feed.ics"})
    monkeypatch.setattr(FEED_CACHE, "feed_text", lambda url: feed)
    page = service.load_page("chris")
    with pytest.raises(BookingRefused, match="slot_taken"):
        service.book(page, form(), link=None, now=NOW)  # 09:30-10:15 Berlin + gap meets 10:00 busy


def test_move_sends_sequence_one_and_moves_the_follow_up(page, outbox):
    add_person()
    service.book(page, form(), link=None, now=NOW)
    booking = service.confirm(page, confirm_token_from(outbox))
    later = WEDNESDAY_0930 + timedelta(days=1)
    moved = service.move(page, booking, later, NOW, by_guest=True)
    assert moved["starts_at"] == later and moved["sequence"] == 1
    assert {calendar_method(message) for _, message in outbox[-2:]} == {("REQUEST", 1)}
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT due_date, status FROM follow_ups WHERE id=%s", (moved["follow_up_id"],))
        assert dict(cursor.fetchone()) == {"due_date": later.date(), "status": "active"}


def test_guest_cannot_change_inside_the_cutoff_but_chris_can(page, outbox):
    service.book(page, form(), link=None, now=NOW)
    booking = service.confirm(page, confirm_token_from(outbox))
    too_close = WEDNESDAY_0930 - timedelta(hours=2)
    with pytest.raises(BookingRefused, match="too_late"):
        service.cancel(page, booking, too_close, by_guest=True)
    cancelled = service.cancel(page, booking, too_close, by_guest=False)
    assert cancelled["status"] == "cancelled"
    assert {calendar_method(message) for _, message in outbox[-2:]} == {("CANCEL", 1)}


def test_cancel_dismisses_the_follow_up(page, outbox):
    add_person()
    service.book(page, form(), link=None, now=NOW)
    booking = service.confirm(page, confirm_token_from(outbox))
    service.cancel(page, booking, NOW, by_guest=True)
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT status FROM follow_ups WHERE id=%s", (booking["follow_up_id"],))
        assert cursor.fetchone()["status"] == "dismissed"


def test_meeting_held_is_logged_once_with_the_booked_minutes(page, outbox):
    person_id = add_person()
    service.book(page, form(), link=None, now=NOW)
    booking = service.confirm(page, confirm_token_from(outbox))
    assert log_meeting_held(get_booking(booking["id"])) is True
    assert log_meeting_held(get_booking(booking["id"])) is False
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT method, duration_minutes FROM people_interactions WHERE person_id=%s", (person_id,))
        assert [dict(row) for row in cursor.fetchall()] == [{"method": "video", "duration_minutes": 45}]
        cursor.execute("SELECT status FROM follow_ups WHERE id=%s", (booking["follow_up_id"],))
        assert cursor.fetchone()["status"] == "completed"
