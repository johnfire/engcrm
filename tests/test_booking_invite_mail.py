"""Booking emails: invite structure that calendar apps recognise, and the words in both languages."""
import email
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from gcrm.booking.booking_texts import describe_time, has_text, text
from gcrm.booking.invite_mail import build_invite_email, build_plain_email
from gcrm.tools import email as email_tools

ROOT = Path(__file__).parents[1]
I18N = ROOT / "gcrm/i18n"
ICS = b"BEGIN:VCALENDAR\r\nMETHOD:REQUEST\r\nBEGIN:VEVENT\r\nUID:x@example\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"


def invite(method="REQUEST"):
    return build_invite_email(sender="termine@example.org", sender_name="Christopher Rehm",
                              recipient="erika@example.com", subject="Termin bestätigt", body="Guten Tag Erika",
                              ics=ICS, method=method)


def test_invite_has_inline_calendar_part_with_method_and_an_attachment():
    parsed = email.message_from_string(invite().as_string())
    assert parsed.get_content_type() == "multipart/mixed"
    alternative, attachment = parsed.get_payload()
    plain, calendar = alternative.get_payload()
    assert plain.get_content_type() == "text/plain"
    assert calendar.get_content_type() == "text/calendar"
    assert calendar.get_param("method") == "REQUEST"
    assert b"UID:x@example" in calendar.get_payload(decode=True)
    assert attachment.get_filename() == "invite.ics"
    assert attachment.get_payload(decode=True) == ICS


def test_cancel_invite_says_cancel():
    parsed = email.message_from_string(invite("CANCEL").as_string())
    alternative, attachment = parsed.get_payload()
    assert alternative.get_payload()[1].get_param("method") == "CANCEL"
    assert attachment.get_filename() == "cancel.ics"


def test_headers_name_the_sender_and_use_its_domain_for_message_id():
    message = invite()
    assert message["From"] == "Christopher Rehm <termine@example.org>"
    assert message["To"] == "erika@example.com"
    assert message["Message-ID"].endswith("@example.org>")


def test_plain_email_keeps_umlauts():
    message = build_plain_email(sender="termine@example.org", sender_name="", recipient="erika@example.com",
                                subject="Bestätigung", body="Grüße")
    parsed = email.message_from_string(message.as_string())
    assert parsed.get_payload()[0].get_payload(decode=True).decode("utf-8") == "Grüße"


def test_time_is_described_in_berlin_time_with_european_dates():
    start = datetime(2026, 12, 8, 9, 30, tzinfo=timezone.utc)
    end = datetime(2026, 12, 8, 10, 15, tzinfo=timezone.utc)
    berlin = ZoneInfo("Europe/Berlin")
    assert describe_time("de", start, end, berlin) == "Dienstag, 08.12.2026, 10:30–11:15 Uhr (Berlin)"
    assert describe_time("en", start, end, berlin) == "Tuesday, 08.12.2026, 10:30–11:15 (Berlin time)"


def test_every_booking_text_exists_in_both_catalogs_with_the_same_placeholders():
    catalogs = {lang: json.loads((I18N / f"{lang}.json").read_text(encoding="utf-8")) for lang in ("de", "en")}
    booking_keys = {lang: {key for key in catalog if key.startswith("booking.")} for lang, catalog in catalogs.items()}
    assert booking_keys["de"] == booking_keys["en"] and len(booking_keys["de"]) > 100
    for key in booking_keys["de"]:
        fields = [set(re.findall(r"\{\{(\w+)\}\}", catalogs[lang][key])) for lang in ("de", "en")]
        assert fields[0] == fields[1], key
    assert "nav.bookings" in catalogs["de"] and "nav.bookings" in catalogs["en"]


def test_every_key_the_booking_code_asks_for_exists():
    """A typo in a key shows as [booking.x] on the page; catch it here instead."""
    sources = list((ROOT / "gcrm/booking").glob("*.py")) + list((ROOT / "gcrm/api/routers").glob("booking_*.py"))
    templates = list((ROOT / "gcrm/ui/templates/booking").glob("*.html")) + [ROOT / "gcrm/ui/templates/bookings.html"]
    asked = set()
    for path in sources:
        asked |= set(re.findall(r'text\([^,]+,\s*"([a-z_]+\.[a-z_]+)"', path.read_text()))
    for path in templates:
        asked |= set(re.findall(r"bt\('([a-z_]+\.[a-z_]+)'", path.read_text()))
    assert asked and all(has_text(key) for key in asked), sorted(key for key in asked if not has_text(key))


def test_unknown_language_falls_back_to_german():
    assert text("fr", "kind.call") == "Telefonat (15 Min.)"


def test_prepared_email_respects_the_global_switch_and_files_a_copy():
    fake_smtp = MagicMock()
    fake_smtp.__enter__.return_value = fake_smtp
    with patch.object(email_tools, "EMAIL_ENABLED", False), \
         patch.object(email_tools.smtplib, "SMTP", return_value=fake_smtp):
        assert email_tools.send_prepared_email(invite(), "erika@example.com") is False
    fake_smtp.sendmail.assert_not_called()
    with patch.object(email_tools, "EMAIL_ENABLED", True), \
         patch.object(email_tools.smtplib, "SMTP", return_value=fake_smtp), \
         patch.object(email_tools, "_append_to_sent") as append:
        assert email_tools.send_prepared_email(invite(), "erika@example.com") is True
    assert fake_smtp.sendmail.call_args.args[1] == ["erika@example.com"]
    append.assert_called_once()
