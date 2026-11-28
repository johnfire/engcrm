"""Busy time from a calendar share feed (Proton "Share with anyone → Limited view").

Parsing is pure: ICS text in, sorted UTC spans out. Fetching sits behind a small
cache that fails closed: when the feed cannot be read and the last good copy is
older than STALE_AFTER, it answers None and the booking page offers no times.
"""
import logging
from collections.abc import Callable
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
import icalendar
import recurring_ical_events

from gcrm.booking.slots import TimeSpan

logger = logging.getLogger(__name__)

FRESH_FOR = timedelta(minutes=5)
STALE_AFTER = timedelta(hours=1)
FETCH_TIMEOUT_SECONDS = 10.0


def _as_utc(moment: date | datetime, zone: ZoneInfo) -> datetime:
    if isinstance(moment, datetime):
        local = moment if moment.tzinfo else moment.replace(tzinfo=zone)
        return local.astimezone(timezone.utc)
    return datetime.combine(moment, time(0), tzinfo=zone).astimezone(timezone.utc)


def _is_busy(event) -> bool:
    is_free = str(event.get("TRANSP", "")).upper() == "TRANSPARENT"
    is_cancelled = str(event.get("STATUS", "")).upper() == "CANCELLED"
    return not (is_free or is_cancelled)


def _event_span(event, zone: ZoneInfo) -> TimeSpan:
    start = event.get("DTSTART").dt
    end_field = event.get("DTEND")
    end = end_field.dt if end_field is not None else start
    return TimeSpan(_as_utc(start, zone), _as_utc(end, zone))


def busy_spans_from_ics(ics_text: str, window: TimeSpan, zone: ZoneInfo) -> list[TimeSpan]:
    """Busy spans inside `window`, repeating events expanded. Floating times and all-day
    events are read in `zone`. Raises ValueError when the text is not a calendar."""
    try:
        calendar = icalendar.Calendar.from_ical(ics_text)
    except Exception as error:
        raise ValueError(f"not a calendar feed: {error}") from error
    if calendar.name != "VCALENDAR":
        raise ValueError("not a calendar feed")
    events = recurring_ical_events.of(calendar).between(window.start, window.end)
    spans = [_event_span(event, zone) for event in events if _is_busy(event)]
    return sorted(spans, key=lambda span: span.start)


def fetch_feed_text(url: str) -> str:
    response = httpx.get(url, timeout=FETCH_TIMEOUT_SECONDS, follow_redirects=True)
    response.raise_for_status()
    return response.text


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class BusyFeedCache:
    """Per-process cache of feed text, keyed by URL. Never raises: a failed fetch
    falls back to the last good copy while it is younger than STALE_AFTER."""

    def __init__(self, fetch: Callable[[str], str] = fetch_feed_text,
                 clock: Callable[[], datetime] = _utc_now):
        self._fetch = fetch
        self._clock = clock
        self._copies: dict[str, tuple[datetime, str]] = {}

    def feed_text(self, url: str) -> str | None:
        now = self._clock()
        fetched_at, text = self._copies.get(url, (None, None))
        if fetched_at is not None and now - fetched_at < FRESH_FOR:
            return text
        try:
            text = self._fetch(url)
            self._copies[url] = (now, text)
            return text
        except Exception as error:
            logger.warning("busy feed fetch failed: %s", type(error).__name__)
        if fetched_at is not None and now - fetched_at < STALE_AFTER:
            return text
        return None
