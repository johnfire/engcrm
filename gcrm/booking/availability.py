"""Which start times a booking type offers right now: open hours minus the busy time of every
linked Proton calendar, minus live bookings and blocks. Fails closed: when any linked calendar
is unreadable (and its last good copy is over an hour old), it answers None, never a guess."""
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from gcrm.booking.booking_store import taken_spans
from gcrm.booking.busy_feed import BusyFeedCache, busy_spans_from_ics
from gcrm.booking.setup_store import list_booking_hours
from gcrm.booking.slots import (
    OpenHours,
    SlotRules,
    TimeSpan,
    calendar_busy_span,
    free_slots,
    open_spans,
)

logger = logging.getLogger(__name__)
FEED_CACHE = BusyFeedCache()
# Fetched side by side, so ten calendars cost one timeout at worst, not ten.
MAX_PARALLEL_FEEDS = 10


def slot_rules(booking_type: dict, settings: dict, minutes: int | None = None) -> SlotRules:
    weekdays = booking_type.get("weekdays")
    return SlotRules(minutes=minutes or booking_type["minutes"], travel_minutes=booking_type["travel_minutes"],
                     gap_minutes=settings["gap_minutes"], weekdays=frozenset(weekdays) if weekdays else None,
                     min_notice=timedelta(hours=settings["min_notice_hours"]),
                     horizon=timedelta(days=settings["horizon_days"]))


def _busy_of_one_feed(url: str | None, window: TimeSpan, zone: ZoneInfo) -> list[TimeSpan] | None:
    """None when the calendar cannot be read; a stored link that no longer decrypts is None too."""
    if url is None:
        return None
    feed_text = FEED_CACHE.feed_text(url)
    if feed_text is None:
        return None
    try:
        return busy_spans_from_ics(feed_text, window, zone)
    except ValueError:
        logger.warning("booking: a calendar feed is not a calendar")
        return None


def _calendar_busy(settings: dict, window: TimeSpan, zone: ZoneInfo) -> list[TimeSpan] | None:
    """Busy time of all linked calendars together, or None when any one of them cannot be read:
    a calendar left out could hold the very hour a guest would book."""
    urls = settings["feed_urls"]
    if not urls:
        return []
    with ThreadPoolExecutor(max_workers=min(len(urls), MAX_PARALLEL_FEEDS)) as pool:
        per_feed = list(pool.map(lambda url: _busy_of_one_feed(url, window, zone), urls))
    if any(events is None for events in per_feed):
        return None
    return [calendar_busy_span(event, settings["gap_minutes"]) for events in per_feed for event in events]


def available_starts(booking_type: dict, settings: dict, now: datetime, *, minutes: int | None = None,
                     except_booking_id: int | None = None) -> list[datetime] | None:
    """Free start times in UTC, or None when busy time cannot be known."""
    zone = ZoneInfo(settings["time_zone"])
    rules = slot_rules(booking_type, settings, minutes)
    window = TimeSpan(now, now + rules.horizon + timedelta(days=1))
    calendar_busy = _calendar_busy(settings, window, zone)
    if calendar_busy is None:
        return None
    booked = taken_spans(window, settings["gap_minutes"], except_booking_id=except_booking_id)
    hours = [OpenHours(row["weekday"], row["opens"], row["closes"]) for row in list_booking_hours()]
    windows = open_spans(hours, now.astimezone(zone).date(), window.end.astimezone(zone).date(), zone)
    return free_slots(windows, calendar_busy + booked, rules, now, zone)
