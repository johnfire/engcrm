"""Free booking slots: open hours minus busy time, with travel, gap, notice and horizon."""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from gcrm.booking.slots import (
    OpenHours,
    SlotRules,
    TimeSpan,
    calendar_busy_span,
    free_slots,
    occupied_span,
    open_spans,
)

BERLIN = ZoneInfo("Europe/Berlin")
MONDAY = date(2026, 12, 7)


def utc(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=BERLIN).astimezone(timezone.utc)


def rules(minutes=30, travel=0, gap=0, weekdays=None, notice_hours=0, horizon_days=60) -> SlotRules:
    return SlotRules(minutes=minutes, travel_minutes=travel, gap_minutes=gap, weekdays=weekdays,
                     min_notice=timedelta(hours=notice_hours), horizon=timedelta(days=horizon_days))


def morning(weekday=0) -> OpenHours:
    return OpenHours(weekday=weekday, opens=time(9, 30), closes=time(12, 0))


def test_open_spans_follow_berlin_wall_clock_across_the_clock_change():
    # 26.10.2026 is the Monday after the switch to winter time; 19.10.2026 is still summer time.
    spans = open_spans([morning()], date(2026, 10, 19), date(2026, 10, 26), BERLIN)
    assert [span.start.astimezone(BERLIN).time() for span in spans] == [time(9, 30), time(9, 30)]
    assert spans[0].start.utcoffset() == timedelta(0)
    assert spans[0].start.hour == 7 and spans[1].start.hour == 8


def test_open_spans_only_on_matching_weekdays():
    spans = open_spans([morning(weekday=1)], MONDAY, MONDAY + timedelta(days=6), BERLIN)
    assert [span.start.date() for span in spans] == [MONDAY + timedelta(days=1)]


def test_slots_step_every_quarter_hour_and_fit_inside_open_hours():
    spans = open_spans([morning()], MONDAY, MONDAY, BERLIN)
    starts = free_slots(spans, [], rules(minutes=45), now=utc(MONDAY, 6))
    assert starts[0] == utc(MONDAY, 9, 30)
    assert starts[-1] == utc(MONDAY, 11, 15)
    assert len(starts) == 8


def test_busy_time_removes_overlapping_slots_only():
    spans = open_spans([morning()], MONDAY, MONDAY, BERLIN)
    busy = [TimeSpan(utc(MONDAY, 10), utc(MONDAY, 10, 30))]
    starts = free_slots(spans, busy, rules(minutes=30), now=utc(MONDAY, 6))
    assert utc(MONDAY, 9, 30) in starts
    assert utc(MONDAY, 9, 45) not in starts
    assert utc(MONDAY, 10, 15) not in starts
    assert utc(MONDAY, 10, 30) in starts


def test_travel_and_gap_keep_distance_from_busy_time():
    spans = open_spans([OpenHours(0, time(9), time(17))], MONDAY, MONDAY, BERLIN)
    busy = [calendar_busy_span(TimeSpan(utc(MONDAY, 12), utc(MONDAY, 13)), gap_minutes=15)]
    starts = free_slots(spans, busy, rules(minutes=60, travel=60, gap=15), now=utc(MONDAY, 6))
    assert utc(MONDAY, 9, 45) in starts       # 9:45-10:45, travel back to 11:45, gap to 12:00
    assert utc(MONDAY, 10) not in starts
    assert utc(MONDAY, 14) not in starts      # busy until 13:00, gap until 13:15, travel needs 60
    assert utc(MONDAY, 14, 15) in starts


def test_calendar_busy_span_adds_the_gap_after_the_event():
    event = TimeSpan(utc(MONDAY, 12), utc(MONDAY, 13))
    assert calendar_busy_span(event, gap_minutes=15) == TimeSpan(utc(MONDAY, 12), utc(MONDAY, 13, 15))


def test_minimum_notice_hides_slots_too_soon():
    spans = open_spans([morning()], MONDAY, MONDAY, BERLIN)
    starts = free_slots(spans, [], rules(minutes=30, notice_hours=2), now=utc(MONDAY, 8, 50))
    assert starts[0] == utc(MONDAY, 11)


def test_horizon_hides_slots_too_far_ahead():
    spans = open_spans([morning()], MONDAY, MONDAY + timedelta(days=14), BERLIN)
    starts = free_slots(spans, [], rules(minutes=30, horizon_days=7), now=utc(MONDAY, 6))
    assert max(starts) < utc(MONDAY, 6) + timedelta(days=7)
    assert min(starts) == utc(MONDAY, 9, 30)


def test_weekday_limit_of_a_type():
    spans = open_spans([morning(0), morning(2)], MONDAY, MONDAY + timedelta(days=2), BERLIN)
    starts = free_slots(spans, [], rules(minutes=60, weekdays=frozenset({2})), now=utc(MONDAY, 6))
    assert {start.astimezone(BERLIN).weekday() for start in starts} == {2}


def test_occupied_span_adds_travel_both_sides_and_gap_after():
    span = occupied_span(utc(MONDAY, 10), minutes=60, travel_minutes=30, gap_minutes=15)
    assert span == TimeSpan(utc(MONDAY, 9, 30), utc(MONDAY, 11, 45))


def test_back_to_back_bookings_respect_the_gap_once():
    spans = open_spans([morning()], MONDAY, MONDAY, BERLIN)
    booked = occupied_span(utc(MONDAY, 10), minutes=15, travel_minutes=0, gap_minutes=15)
    starts = free_slots(spans, [booked], rules(minutes=15, gap=15), now=utc(MONDAY, 6))
    assert utc(MONDAY, 9, 30) in starts      # 9:30-9:45 + gap ends 10:00 exactly
    assert utc(MONDAY, 9, 45) not in starts
    assert utc(MONDAY, 10, 15) not in starts
    assert utc(MONDAY, 10, 30) in starts


def test_time_span_rejects_end_before_start():
    try:
        TimeSpan(utc(MONDAY, 10), utc(MONDAY, 9))
    except ValueError:
        return
    raise AssertionError("TimeSpan accepted an end before its start")


def test_time_span_requires_aware_datetimes():
    try:
        TimeSpan(datetime(2026, 12, 7, 9), datetime(2026, 12, 7, 10))
    except ValueError:
        return
    raise AssertionError("TimeSpan accepted naive datetimes")
