"""Words for the booking pages and emails, from the shared catalogs (gcrm/i18n, keys booking.*).

A booking speaks the language its booker chose (de or en), not a signed-in user's, so
every lookup names its language. Dates are written 08.12.2026 in both (gcrm/dates.py).
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from gcrm.i18n import translate

LANGUAGES = ("de", "en")


def booking_language(language: str | None) -> str:
    """The booker's language; anything else reads as German, the page's home language."""
    return language if language in LANGUAGES else "de"


def text(language: str, key: str, **values) -> str:
    return translate(f"booking.{key}", booking_language(language), **values)


def has_text(key: str) -> bool:
    return translate(f"booking.{key}", "en") != f"[booking.{key}]"


def weekday_name(language: str, weekday: int) -> str:
    """Monday is 0, as in datetime.weekday()."""
    return text(language, f"weekday.{weekday}")


def describe_time(language: str, starts_at: datetime, ends_at: datetime, zone: ZoneInfo) -> str:
    start, end = starts_at.astimezone(zone), ends_at.astimezone(zone)
    return text(language, "when", weekday=weekday_name(language, start.weekday()), day=start.strftime("%d.%m.%Y"),
                start=start.strftime("%H:%M"), end=end.strftime("%H:%M"))
