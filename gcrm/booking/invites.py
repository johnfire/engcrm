"""Calendar invites (.ics) for bookings, readable by Proton, Google, Outlook and Apple.

Times are written in UTC (…Z) so every app shows them in its own time zone with no
VTIMEZONE block to get wrong. A booking keeps one UID for life; a move is a new
REQUEST and a cancel a CANCEL, each with a higher SEQUENCE, so calendars update the
event in place instead of adding a second one.
"""
from dataclasses import dataclass
from datetime import datetime

import icalendar

METHODS = {"REQUEST": "CONFIRMED", "CANCEL": "CANCELLED"}
PRODUCT_ID = "-//engcrm//booking//EN"


@dataclass(frozen=True)
class InviteDetails:
    uid: str
    sequence: int
    start: datetime
    end: datetime
    summary: str
    description: str
    location: str
    organizer_email: str
    organizer_name: str
    host_email: str
    guest_email: str
    guest_name: str
    stamped_at: datetime


def _attendee(email: str, name: str, status: str) -> icalendar.vCalAddress:
    attendee = icalendar.vCalAddress(f"mailto:{email}")
    attendee.params["CN"] = icalendar.vText(name)
    attendee.params["ROLE"] = icalendar.vText("REQ-PARTICIPANT")
    attendee.params["PARTSTAT"] = icalendar.vText(status)
    attendee.params["RSVP"] = icalendar.vText("TRUE")
    return attendee


def _organizer(email: str, name: str) -> icalendar.vCalAddress:
    organizer = icalendar.vCalAddress(f"mailto:{email}")
    organizer.params["CN"] = icalendar.vText(name)
    return organizer


def _event(details: InviteDetails, status: str) -> icalendar.Event:
    event = icalendar.Event()
    event.add("uid", details.uid)
    event.add("sequence", details.sequence)
    event.add("dtstamp", details.stamped_at)
    event.add("dtstart", details.start)
    event.add("dtend", details.end)
    event.add("summary", details.summary)
    event.add("description", details.description)
    event.add("location", details.location)
    event.add("status", status)
    event.add("organizer", _organizer(details.organizer_email, details.organizer_name))
    event.add("attendee", _attendee(details.host_email, details.organizer_name, "ACCEPTED"))
    event.add("attendee", _attendee(details.guest_email, details.guest_name, "NEEDS-ACTION"))
    return event


def build_invite(details: InviteDetails, method: str) -> bytes:
    """The .ics bytes for a REQUEST (new or moved booking) or a CANCEL."""
    if method not in METHODS:
        raise ValueError(f"unsupported invite method: {method}")
    calendar = icalendar.Calendar()
    calendar.add("prodid", PRODUCT_ID)
    calendar.add("version", "2.0")
    calendar.add("calscale", "GREGORIAN")
    calendar.add("method", method)
    calendar.add_component(_event(details, METHODS[method]))
    return calendar.to_ical()
