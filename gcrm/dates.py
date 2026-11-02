"""Dates for people: shown and typed European style, 28.10.2026, in every
language. Stored, sorted and sent between machines (API, exports) as ISO."""
import re
from datetime import date, datetime

_TYPED = re.compile(r"(\d{1,2})[./-](\d{1,2})(?:[./-](\d{2}|\d{4})?)?")


def _as_moment(value) -> date | datetime | None:
    """A date or datetime from either, or from an ISO string; None when it is not one."""
    if isinstance(value, (date, datetime)):
        return value
    text = str(value).strip()
    try:
        return datetime.fromisoformat(text) if len(text) > 10 else date.fromisoformat(text)
    except ValueError:
        return None


def format_day(value) -> str:
    """28.10.2026 — or "" for nothing, or the text unchanged if it is not a date."""
    if value is None or value == "":
        return ""
    moment = _as_moment(value)
    return moment.strftime("%d.%m.%Y") if moment else str(value)


def format_day_time(value) -> str:
    """28.10.2026 14:07, the time as stored; just the day when there is no time."""
    if value is None or value == "":
        return ""
    moment = _as_moment(value)
    if isinstance(moment, datetime):
        return moment.strftime("%d.%m.%Y %H:%M")
    return format_day(value)


def parse_day(value, today: date | None = None) -> date | None:
    """A typed day: 28.10.2026, 28.10.26, 28/10/2026, 28.10. (this year) or ISO
    2026-10-28. None when blank. Raises ValueError for anything else, including
    impossible days and American month-first dates."""
    text = (value or "").strip()
    if not text:
        return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return date.fromisoformat(text)
    match = _TYPED.fullmatch(text)
    if not match:
        raise ValueError("a day must look like 28.10.2026")
    day, month, year = match.groups()
    this_year = (today or date.today()).year
    full_year = this_year if year is None else int(year) + (2000 if len(year) == 2 else 0)
    return date(full_year, int(month), int(day))
