"""Calendar invites (.ics) for a booking: request, move and cancel share one UID."""
from datetime import datetime, timezone

import icalendar

from gcrm.booking.invites import InviteDetails, build_invite

START = datetime(2026, 12, 8, 9, 30, tzinfo=timezone.utc)
END = datetime(2026, 12, 8, 10, 15, tzinfo=timezone.utc)


def details(**changes) -> InviteDetails:
    fields = dict(
        uid="booking-41@engcrm.example", sequence=0, start=START, end=END,
        summary="Video meeting: Erika Musterfrau / Christopher Rehm",
        description="Topic: AI in quality control; line one\nline two, with comma",
        location="https://meet.example/room-chris",
        organizer_email="termine@example.org", organizer_name="Christopher Rehm",
        host_email="host@example.net", guest_email="erika@example.com", guest_name="Erika Musterfrau",
        stamped_at=datetime(2026, 11, 28, 12, tzinfo=timezone.utc),
    )
    fields.update(changes)
    return InviteDetails(**fields)


def parsed_event(ics: bytes):
    calendar = icalendar.Calendar.from_ical(ics)
    events = [part for part in calendar.walk() if part.name == "VEVENT"]
    assert len(events) == 1
    return calendar, events[0]


def test_request_carries_method_uid_and_utc_times():
    calendar, event = parsed_event(build_invite(details(), "REQUEST"))
    assert str(calendar["METHOD"]) == "REQUEST"
    assert str(event["UID"]) == "booking-41@engcrm.example"
    assert event["DTSTART"].dt == START and event["DTEND"].dt == END
    assert b"DTSTART:20261208T093000Z" in build_invite(details(), "REQUEST")
    assert int(event["SEQUENCE"]) == 0
    assert str(event["STATUS"]) == "CONFIRMED"


def test_organizer_and_both_attendees():
    _, event = parsed_event(build_invite(details(), "REQUEST"))
    assert str(event["ORGANIZER"]).lower() == "mailto:termine@example.org"
    attendees = {str(attendee).lower() for attendee in event["ATTENDEE"]}
    assert attendees == {"mailto:host@example.net", "mailto:erika@example.com"}


def test_text_fields_survive_commas_semicolons_and_newlines():
    _, event = parsed_event(build_invite(details(), "REQUEST"))
    assert str(event["DESCRIPTION"]) == "Topic: AI in quality control; line one\nline two, with comma"
    assert str(event["LOCATION"]) == "https://meet.example/room-chris"


def test_cancel_keeps_uid_and_raises_sequence():
    calendar, event = parsed_event(build_invite(details(sequence=2), "CANCEL"))
    assert str(calendar["METHOD"]) == "CANCEL"
    assert str(event["UID"]) == "booking-41@engcrm.example"
    assert int(event["SEQUENCE"]) == 2
    assert str(event["STATUS"]) == "CANCELLED"


def test_long_lines_are_folded_to_75_octets():
    ics = build_invite(details(description="x" * 400), "REQUEST")
    assert all(len(line) <= 75 for line in ics.split(b"\r\n"))


def test_unknown_method_is_refused():
    try:
        build_invite(details(), "PUBLISH")
    except ValueError:
        return
    raise AssertionError("build_invite accepted an unsupported method")
