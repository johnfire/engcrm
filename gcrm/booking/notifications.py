"""Which emails go out for each booking event, to whom, with which invite.

Every sender here returns True/False and never raises: a mail failure must not undo a
booking. Invite results are written onto the booking so Chris sees a failed send and can
send it again.
"""
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from gcrm.booking.booking_store import manage_token_of, record_invite_result
from gcrm.booking.booking_texts import describe_time, text
from gcrm.booking.invite_mail import build_invite_email, build_plain_email
from gcrm.booking.invites import InviteDetails, build_invite
from gcrm.config import APP_PUBLIC_URL
from gcrm.tools.email import send_prepared_email

logger = logging.getLogger(__name__)
INVITE_METHODS = {"invite": "REQUEST", "moved": "REQUEST", "cancelled": "CANCEL"}


def public_link(slug: str, path: str) -> str:
    return f"{APP_PUBLIC_URL}/book/{slug}/{path}"


def _place(booking: dict, settings: dict, language: str) -> str:
    if booking["kind"] == "visit":
        return text(language, "place.visit", address=booking["visit_address"])
    if booking["kind"] == "call":
        return text(language, "place.call", phone=booking["phone"])
    return text(language, "place.video", room=settings["room_link"]) if settings["room_link"] else ""


def _words(booking: dict, settings: dict, slug: str) -> dict:
    language = booking["language"]
    zone = ZoneInfo(settings["time_zone"])
    return {
        "guest": booking["guest_name"], "host": settings["organizer_name"], "email": booking["guest_email"],
        "kind": text(language, f"kind.{booking['kind']}"), "company": booking["company"] or "–",
        "topic": booking["topic"] or "–", "place": _place(booking, settings, language),
        "when": describe_time(language, booking["starts_at"], booking["ends_at"], zone),
        "day": booking["starts_at"].astimezone(zone).strftime("%d.%m.%Y"),
        "manage": public_link(slug, f"manage/{manage_token_of(booking)}"),
        "admin": f"{APP_PUBLIC_URL}/bookings",
    }


def _send(message, recipient: str) -> bool:
    try:
        return send_prepared_email(message, recipient)
    except Exception:
        logger.exception("booking mail to %s failed", recipient)
        return False


def _plain(settings: dict, recipient: str, subject: str, body: str) -> bool:
    if not settings["organizer_email"] or not recipient:
        return False
    message = build_plain_email(sender=settings["organizer_email"], sender_name=settings["organizer_name"],
                                recipient=recipient, subject=subject, body=body)
    return _send(message, recipient)


def _notify_host(event: str, language: str, words: dict, settings: dict, ics: bytes | None = None) -> bool:
    event_name = text(language, f"event.{event}")
    subject = text(language, "subject.host", event=event_name, **words)
    body = text(language, "body.host", event=event_name, **words)
    if ics is None:
        return _plain(settings, settings["host_email"], subject, body)
    message = build_invite_email(sender=settings["organizer_email"], sender_name=settings["organizer_name"],
                                 recipient=settings["host_email"], subject=subject, body=body, ics=ics,
                                 method=INVITE_METHODS[event])
    return _send(message, settings["host_email"])


def send_confirm_request(booking: dict, settings: dict, slug: str, confirm_token: str) -> bool:
    words = _words(booking, settings, slug)
    link = public_link(slug, f"confirm/{confirm_token}")
    return _plain(settings, booking["guest_email"], text(booking["language"], "subject.confirm", **words),
                  text(booking["language"], "body.confirm", link=link, **words))


def send_request_received(booking: dict, settings: dict, slug: str) -> bool:
    words = _words(booking, settings, slug)
    sent = _plain(settings, booking["guest_email"], text(booking["language"], "subject.requested", **words),
                  text(booking["language"], "body.requested", **words))
    _notify_host("requested", booking["language"], words, settings)
    return sent


def send_declined(booking: dict, settings: dict, slug: str) -> bool:
    words = _words(booking, settings, slug)
    return _plain(settings, booking["guest_email"], text(booking["language"], "subject.declined", **words),
                  text(booking["language"], "body.declined", **words))


def invite_ics(booking: dict, settings: dict, slug: str, method: str = "REQUEST") -> bytes:
    words = _words(booking, settings, slug)
    details = InviteDetails(
        uid=booking["ics_uid"], sequence=booking["sequence"], start=booking["starts_at"], end=booking["ends_at"],
        summary=text(booking["language"], "summary", **words),
        description="\n".join(part for part in (words["topic"] if booking["topic"] else "", words["manage"]) if part),
        location=words["place"], organizer_email=settings["organizer_email"],
        organizer_name=settings["organizer_name"], host_email=settings["host_email"],
        guest_email=booking["guest_email"], guest_name=booking["guest_name"],
        stamped_at=datetime.now(timezone.utc))
    return build_invite(details, method)


def send_invites(booking: dict, settings: dict, slug: str, event: str) -> bool:
    """`event` is invite, moved or cancelled. Both the booker and Chris get the .ics."""
    words = _words(booking, settings, slug)
    ics = invite_ics(booking, settings, slug, INVITE_METHODS[event])
    message = build_invite_email(sender=settings["organizer_email"], sender_name=settings["organizer_name"],
                                 recipient=booking["guest_email"],
                                 subject=text(booking["language"], f"subject.{event}", **words),
                                 body=text(booking["language"], f"body.{event}", **words),
                                 ics=ics, method=INVITE_METHODS[event])
    guest_sent = bool(settings["organizer_email"]) and _send(message, booking["guest_email"])
    host_sent = _notify_host(event, booking["language"], words, settings, ics)
    error = "" if guest_sent and host_sent else f"{event}: guest={'ok' if guest_sent else 'failed'}, " \
                                                  f"host={'ok' if host_sent else 'failed'}"
    record_invite_result(booking["id"], error)
    return guest_sent and host_sent
