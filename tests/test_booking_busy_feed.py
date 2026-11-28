"""Busy time from a calendar share feed (Proton "Limited view" ICS)."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from gcrm.booking.busy_feed import BusyFeedCache, busy_spans_from_ics
from gcrm.booking.slots import TimeSpan

BERLIN = ZoneInfo("Europe/Berlin")

FEED = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Example//Feed//EN
BEGIN:VTIMEZONE
TZID:Europe/Berlin
BEGIN:STANDARD
DTSTART:19701025T030000
RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU
TZOFFSETFROM:+0200
TZOFFSETTO:+0100
END:STANDARD
BEGIN:DAYLIGHT
DTSTART:19700329T020000
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU
TZOFFSETFROM:+0100
TZOFFSETTO:+0200
END:DAYLIGHT
END:VTIMEZONE
BEGIN:VEVENT
UID:timed-utc
DTSTAMP:20261101T000000Z
DTSTART:20261207T090000Z
DTEND:20261207T100000Z
SUMMARY:Busy
END:VEVENT
BEGIN:VEVENT
UID:timed-berlin
DTSTAMP:20261101T000000Z
DTSTART;TZID=Europe/Berlin:20261208T140000
DTEND;TZID=Europe/Berlin:20261208T150000
SUMMARY:Busy
END:VEVENT
BEGIN:VEVENT
UID:weekly
DTSTAMP:20261101T000000Z
DTSTART;TZID=Europe/Berlin:20261102T080000
DTEND;TZID=Europe/Berlin:20261102T083000
RRULE:FREQ=WEEKLY;BYDAY=MO
SUMMARY:Busy
END:VEVENT
BEGIN:VEVENT
UID:all-day
DTSTAMP:20261101T000000Z
DTSTART;VALUE=DATE:20261210
DTEND;VALUE=DATE:20261211
SUMMARY:Busy
END:VEVENT
BEGIN:VEVENT
UID:free-time
DTSTAMP:20261101T000000Z
DTSTART:20261209T090000Z
DTEND:20261209T100000Z
TRANSP:TRANSPARENT
SUMMARY:Free
END:VEVENT
BEGIN:VEVENT
UID:cancelled
DTSTAMP:20261101T000000Z
DTSTART:20261209T120000Z
DTEND:20261209T130000Z
STATUS:CANCELLED
SUMMARY:Busy
END:VEVENT
END:VCALENDAR
"""

WEEK = TimeSpan(datetime(2026, 12, 7, tzinfo=timezone.utc), datetime(2026, 12, 14, tzinfo=timezone.utc))


def berlin(day, hour, minute=0):
    return datetime(2026, 12, day, hour, minute, tzinfo=BERLIN).astimezone(timezone.utc)


def test_timed_events_become_utc_spans():
    spans = busy_spans_from_ics(FEED, WEEK, BERLIN)
    assert TimeSpan(datetime(2026, 12, 7, 9, tzinfo=timezone.utc), datetime(2026, 12, 7, 10, tzinfo=timezone.utc)) in spans
    assert TimeSpan(berlin(8, 14), berlin(8, 15)) in spans


def test_repeating_events_are_expanded_inside_the_window():
    spans = busy_spans_from_ics(FEED, WEEK, BERLIN)
    assert TimeSpan(berlin(7, 8), berlin(7, 8, 30)) in spans
    assert all(span.start.astimezone(BERLIN).day != 30 for span in spans)


def test_all_day_events_block_the_whole_berlin_day():
    spans = busy_spans_from_ics(FEED, WEEK, BERLIN)
    assert TimeSpan(berlin(10, 0), berlin(11, 0)) in spans


def test_free_and_cancelled_events_are_ignored():
    spans = busy_spans_from_ics(FEED, WEEK, BERLIN)
    starts = {span.start for span in spans}
    assert datetime(2026, 12, 9, 9, tzinfo=timezone.utc) not in starts   # TRANSP:TRANSPARENT
    assert datetime(2026, 12, 9, 12, tzinfo=timezone.utc) not in starts  # STATUS:CANCELLED


def test_spans_are_in_time_order_and_all_utc():
    spans = busy_spans_from_ics(FEED, WEEK, BERLIN)
    assert spans == sorted(spans, key=lambda span: span.start)
    assert all(span.start.utcoffset() == timedelta(0) for span in spans)
    assert len(spans) == 4


def test_garbage_feed_raises_a_value_error():
    with pytest.raises(ValueError):
        busy_spans_from_ics("<html>Not a calendar</html>", WEEK, BERLIN)


class FakeClock:
    def __init__(self):
        self.moment = datetime(2026, 12, 7, 8, tzinfo=timezone.utc)

    def __call__(self):
        return self.moment


def test_cache_reuses_a_fresh_copy_and_refetches_after_it_ages():
    clock, calls = FakeClock(), []
    cache = BusyFeedCache(fetch=lambda url: calls.append(url) or FEED, clock=clock)
    assert cache.feed_text("https://calendar.example/feed.ics") == FEED
    clock.moment += timedelta(minutes=4)
    cache.feed_text("https://calendar.example/feed.ics")
    assert len(calls) == 1
    clock.moment += timedelta(minutes=2)
    cache.feed_text("https://calendar.example/feed.ics")
    assert len(calls) == 2


def test_cache_serves_the_last_good_copy_for_an_hour_when_fetching_fails():
    clock = FakeClock()
    answers = iter([FEED])

    def fetch(url):
        return next(answers)  # second call raises StopIteration, like a network failure

    cache = BusyFeedCache(fetch=fetch, clock=clock)
    cache.feed_text("https://calendar.example/feed.ics")
    clock.moment += timedelta(minutes=50)
    assert cache.feed_text("https://calendar.example/feed.ics") == FEED
    clock.moment += timedelta(minutes=15)
    assert cache.feed_text("https://calendar.example/feed.ics") is None


def test_cache_returns_none_when_the_first_fetch_fails():
    def fetch(url):
        raise OSError("unreachable")

    assert BusyFeedCache(fetch=fetch, clock=FakeClock()).feed_text("https://calendar.example/feed.ics") is None
