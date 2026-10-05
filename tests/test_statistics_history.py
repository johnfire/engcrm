"""Buckets for the over-time charts."""
from datetime import date

from gcrm.tools.statistics_history import bucket_start, bucket_starts


def test_weekly_buckets_are_the_last_twelve_mondays():
    starts = bucket_starts("week", date(2026, 10, 15))
    assert len(starts) == 12 and starts[-1] == date(2026, 10, 12) and starts[0] == date(2026, 7, 27)


def test_monthly_buckets_cross_the_year():
    starts = bucket_starts("month", date(2026, 2, 10))
    assert starts[0] == date(2025, 3, 1) and starts[-1] == date(2026, 2, 1) and len(starts) == 12


def test_yearly_buckets_are_five_years():
    assert bucket_starts("year", date(2026, 6, 1)) == [date(y, 1, 1) for y in range(2022, 2027)]


def test_bucket_start():
    assert bucket_start("week", date(2026, 10, 18)) == date(2026, 10, 12)
    assert bucket_start("month", date(2026, 10, 18)) == date(2026, 10, 1)
    assert bucket_start("year", date(2026, 10, 18)) == date(2026, 1, 1)
