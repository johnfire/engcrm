"""Which start times a booking type offers right now: open hours minus Proton busy time,
minus live bookings and blocks. Fails closed: when the feed is set up but unreadable
(and the last good copy is over an hour old), it answers None, never a guess."""
import logging
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


def slot_rules(booking_type: dict, settings: dict, minutes: int | None = None) -> SlotRules:
    weekdays = booking_type.get("weekdays")
    return SlotRules(minutes=minutes or booking_type["minutes"], travel_minutes=booking_type["travel_minutes"],
                     gap_minutes=settings["gap_minutes"], weekdays=frozenset(weekdays) if weekdays else None,
                     min_notice=timedelta(hours=settings["min_notice_hours"]),
                     horizon=timedelta(days=settings["horizon_days"]))


def _calendar_busy(settings: dict, window: TimeSpan, zone: ZoneInfo) -> list[TimeSpan] | None:
    if not settings["feed_url"]:
        return []
    feed_text = FEED_CACHE.feed_text(settings["feed_url"])
    if feed_text is None:
        return None
    try:
        events = busy_spans_from_ics(feed_text, window, zone)
    except ValueError:
        logger.warning("booking: calendar feed is not a calendar")
        return None
    return [calendar_busy_span(event, settings["gap_minutes"]) for event in events]


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
