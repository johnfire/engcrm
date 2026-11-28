"""Free booking slots: weekly open hours minus busy time.

Pure functions only: no database, no network, no clock. Every datetime is
timezone-aware; open hours are Berlin wall-clock times turned into UTC day by day,
so 09:30 stays 09:30 across the clock changes.

One rule for "occupied" is used everywhere, here and in the database's exclusion
constraint: a booking occupies [start - travel, end + travel + gap). A calendar
event occupies [start, end + gap). So two things always sit at least one gap apart.
"""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

SLOT_STEP = timedelta(minutes=15)


@dataclass(frozen=True)
class TimeSpan:
    start: datetime
    end: datetime

    def __post_init__(self):
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("TimeSpan needs timezone-aware datetimes")
        if self.end < self.start:
            raise ValueError("TimeSpan ends before it starts")

    def overlaps(self, other: "TimeSpan") -> bool:
        return self.start < other.end and other.start < self.end


@dataclass(frozen=True)
class OpenHours:
    """One weekly window: weekday 0 = Monday, times in the booking time zone."""
    weekday: int
    opens: time
    closes: time


@dataclass(frozen=True)
class SlotRules:
    minutes: int
    travel_minutes: int
    gap_minutes: int
    weekdays: frozenset[int] | None
    min_notice: timedelta
    horizon: timedelta


def occupied_span(start: datetime, minutes: int, travel_minutes: int, gap_minutes: int) -> TimeSpan:
    travel = timedelta(minutes=travel_minutes)
    end = start + timedelta(minutes=minutes)
    return TimeSpan(start - travel, end + travel + timedelta(minutes=gap_minutes))


def calendar_busy_span(event: TimeSpan, gap_minutes: int) -> TimeSpan:
    return TimeSpan(event.start, event.end + timedelta(minutes=gap_minutes))


def _days(first_day: date, last_day: date) -> list[date]:
    return [first_day + timedelta(days=offset) for offset in range((last_day - first_day).days + 1)]


def _window_on(day: date, hours: OpenHours, zone: ZoneInfo) -> TimeSpan:
    opens = datetime.combine(day, hours.opens, tzinfo=zone).astimezone(timezone.utc)
    closes = datetime.combine(day, hours.closes, tzinfo=zone).astimezone(timezone.utc)
    return TimeSpan(opens, closes)


def open_spans(weekly_hours: list[OpenHours], first_day: date, last_day: date, zone: ZoneInfo) -> list[TimeSpan]:
    """Every open window between two days (inclusive), in UTC, in time order."""
    windows = [
        _window_on(day, hours, zone)
        for day in _days(first_day, last_day)
        for hours in weekly_hours
        if hours.weekday == day.weekday() and hours.closes > hours.opens
    ]
    return sorted(windows, key=lambda window: window.start)


def _candidate_starts(window: TimeSpan, minutes: int) -> list[datetime]:
    length = timedelta(minutes=minutes)
    starts = []
    start = window.start
    while start + length <= window.end:
        starts.append(start)
        start += SLOT_STEP
    return starts


def _is_free(start: datetime, rules: SlotRules, busy: list[TimeSpan], zone: ZoneInfo) -> bool:
    if rules.weekdays is not None and start.astimezone(zone).weekday() not in rules.weekdays:
        return False
    needed = occupied_span(start, rules.minutes, rules.travel_minutes, rules.gap_minutes)
    return not any(needed.overlaps(taken) for taken in busy)


def free_slots(windows: list[TimeSpan], busy: list[TimeSpan], rules: SlotRules, now: datetime,
               zone: ZoneInfo = ZoneInfo("Europe/Berlin")) -> list[datetime]:
    """Start times (UTC) a booking of these rules can take. `busy` holds occupied spans:
    other bookings via occupied_span(), calendar events via calendar_busy_span()."""
    earliest = now + rules.min_notice
    latest = now + rules.horizon
    return [
        start
        for window in windows
        for start in _candidate_starts(window, rules.minutes)
        if earliest <= start < latest and _is_free(start, rules, busy, zone)
    ]
