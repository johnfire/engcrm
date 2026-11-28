"""Busy time from several Proton calendars: their union counts, and one unreadable calendar closes the page."""
import threading
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from gcrm.booking import availability
from gcrm.booking.slots import TimeSpan

BERLIN = ZoneInfo("Europe/Berlin")
WINDOW = TimeSpan(datetime(2027, 3, 1, tzinfo=timezone.utc), datetime(2027, 3, 10, tzinfo=timezone.utc))


def calendar(*events: tuple[str, str]) -> str:
    body = "".join(f"BEGIN:VEVENT\r\nUID:{start}\r\nDTSTAMP:20270101T000000Z\r\nDTSTART:{start}\r\nDTEND:{end}\r\n"
                   "END:VEVENT\r\n" for start, end in events)
    return f"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//x//x//EN\r\n{body}END:VCALENDAR\r\n"


def busy(monkeypatch, feeds: dict[str, str | None], gap: int = 0):
    monkeypatch.setattr(availability.FEED_CACHE, "feed_text", feeds.get)
    return availability._calendar_busy({"feed_urls": list(feeds), "gap_minutes": gap}, WINDOW, BERLIN)


def at(day: int, hour: int) -> datetime:
    return datetime(2027, 3, day, hour, tzinfo=timezone.utc)


def test_no_linked_calendar_blocks_nothing(monkeypatch):
    assert busy(monkeypatch, {}) == []


def test_busy_time_of_every_calendar_counts(monkeypatch):
    spans = busy(monkeypatch, {"https://cal.example/business": calendar(("20270303T090000Z", "20270303T100000Z")),
                               "https://cal.example/art": calendar(("20270304T140000Z", "20270304T160000Z"))})
    assert sorted((span.start, span.end) for span in spans) == [(at(3, 9), at(3, 10)), (at(4, 14), at(4, 16))]


def test_the_gap_is_added_after_each_calendar_event(monkeypatch):
    spans = busy(monkeypatch, {"https://cal.example/business": calendar(("20270303T090000Z", "20270303T100000Z"))},
                 gap=15)
    assert spans[0].end == datetime(2027, 3, 3, 10, 15, tzinfo=timezone.utc)


@pytest.mark.parametrize("broken", [None, "this is not a calendar"])
def test_one_unreadable_calendar_closes_the_page(monkeypatch, broken):
    feeds = {"https://cal.example/business": calendar(("20270303T090000Z", "20270303T100000Z")),
             "https://cal.example/art": broken}
    assert busy(monkeypatch, feeds) is None


def test_calendars_are_fetched_side_by_side(monkeypatch):
    """Ten slow calendars must cost one wait, not ten."""
    started, release = threading.Barrier(10, timeout=5), calendar()

    def fetch(url):
        started.wait()  # only returns once all ten fetches are running at the same time
        return release

    monkeypatch.setattr(availability.FEED_CACHE, "feed_text", fetch)
    settings = {"feed_urls": [f"https://cal.example/{number}" for number in range(10)], "gap_minutes": 0}
    assert availability._calendar_busy(settings, WINDOW, BERLIN) == []
