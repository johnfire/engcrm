"""Windows and pace for the contract-flow graphs: pure date and money arithmetic."""
from datetime import date
from decimal import Decimal

import pytest

from gcrm.flow_math import (
    DEFAULT_FLOW,
    FLOW_RANGES,
    bucket_end,
    bucket_start,
    daily_pace,
    flow_buckets,
)

D = Decimal
TODAY = date(2026, 11, 18)          # a Wednesday


def test_the_first_three_ranges_are_three_months_a_year_and_the_whole_business():
    assert FLOW_RANGES[:3] == ("3m", "year", "all") and DEFAULT_FLOW in FLOW_RANGES


def test_bucket_boundaries():
    assert bucket_start("week", date(2026, 11, 18)) == date(2026, 11, 16)          # the Monday
    assert bucket_start("week", date(2026, 11, 16)) == date(2026, 11, 16)
    assert bucket_start("month", date(2026, 11, 18)) == date(2026, 11, 1)
    assert bucket_start("year", date(2026, 11, 18)) == date(2026, 1, 1)
    assert bucket_end("week", date(2026, 11, 16)) == date(2026, 11, 22)
    assert bucket_end("month", date(2026, 2, 1)) == date(2026, 2, 28)
    assert bucket_end("month", date(2028, 2, 1)) == date(2028, 2, 29)
    assert bucket_end("year", date(2026, 1, 1)) == date(2026, 12, 31)
    with pytest.raises(ValueError):
        bucket_start("day", TODAY)


def test_three_months_is_thirteen_weeks_ending_with_this_week():
    granularity, starts = flow_buckets("3m", TODAY)
    assert granularity == "week" and len(starts) == 13
    assert starts[0] == date(2026, 8, 24) and starts[-1] == date(2026, 11, 16)
    assert all(s.weekday() == 0 for s in starts) and starts == sorted(starts)


def test_a_year_is_twelve_months_ending_with_this_month():
    granularity, starts = flow_buckets("year", TODAY)
    assert granularity == "month" and len(starts) == 12
    assert starts[0] == date(2025, 12, 1) and starts[-1] == date(2026, 11, 1)


def test_the_whole_business_runs_from_its_first_month_to_this_month():
    granularity, starts = flow_buckets("all", TODAY, first_month=date(2026, 10, 17))
    assert granularity == "month" and starts == [date(2026, 10, 1), date(2026, 11, 1)]


def test_without_a_first_month_the_whole_business_is_just_this_month_and_a_future_start_is_clamped():
    assert flow_buckets("all", TODAY) == ("month", [date(2026, 11, 1)])
    assert flow_buckets("all", TODAY, first_month=date(2027, 3, 1)) == ("month", [date(2026, 11, 1)])


def test_a_long_history_is_shown_by_year():
    granularity, starts = flow_buckets("all", TODAY, first_month=date(2020, 3, 1))
    assert granularity == "year" and starts == [date(y, 1, 1) for y in range(2020, 2027)]
    granularity, starts = flow_buckets("all", TODAY, first_month=date(2022, 12, 1))   # exactly 48 months
    assert granularity == "month" and len(starts) == 48


def test_an_unknown_range_is_refused():
    with pytest.raises(ValueError):
        flow_buckets("decade", TODAY)


SUPPORT = {"amount_eur": D("1500"), "covers_from": date(2026, 10, 1), "payments": 6, "confirmed": True}


def _sum(pace, field, first, last):
    days = [d for d in pace if first <= d <= last]
    return sum((pace[d][field] for d in days), D("0"))


def test_the_target_and_the_covering_income_are_spread_evenly_over_the_days_of_each_month():
    pace = daily_pace(D("5000"), [SUPPORT], date(2026, 10, 1), date(2026, 10, 1), date(2026, 11, 30))
    assert len(pace) == 61
    assert _sum(pace, "target", date(2026, 10, 1), date(2026, 10, 31)).quantize(D("0.01")) == D("5000.00")
    assert _sum(pace, "target", date(2026, 11, 1), date(2026, 11, 30)).quantize(D("0.01")) == D("5000.00")
    assert _sum(pace, "covered", date(2026, 10, 1), date(2026, 11, 30)).quantize(D("0.01")) == D("3000.00")
    assert pace[date(2026, 11, 5)]["target"].quantize(D("0.01")) == D("166.67")          # 5000 / 30 days


def test_days_before_the_business_started_have_no_target():
    pace = daily_pace(D("5000"), [], date(2026, 10, 1), date(2026, 9, 28), date(2026, 10, 2))
    assert [pace[date(2026, 9, d)]["target"] for d in (28, 29, 30)] == [D("0")] * 3
    assert pace[date(2026, 10, 1)]["target"] > 0


def test_a_partial_range_gives_only_the_days_asked_for():
    pace = daily_pace(D("3100"), [], None, date(2026, 10, 10), date(2026, 10, 12))
    assert sorted(pace) == [date(2026, 10, 10), date(2026, 10, 11), date(2026, 10, 12)]
    assert pace[date(2026, 10, 10)]["target"] == D("100")                                 # 3100 / 31 days


def test_without_a_need_the_target_is_zero_but_income_still_counts_and_unconfirmed_income_does_not():
    maybe = {**SUPPORT, "confirmed": False}
    pace = daily_pace(None, [SUPPORT, maybe], None, date(2026, 10, 1), date(2026, 10, 31))
    assert _sum(pace, "target", date(2026, 10, 1), date(2026, 10, 31)) == D("0")
    assert _sum(pace, "covered", date(2026, 10, 1), date(2026, 10, 31)).quantize(D("0.01")) == D("1500.00")


def test_the_outlook_is_a_further_range_and_not_the_default():
    assert FLOW_RANGES == ("3m", "year", "all", "outlook") and DEFAULT_FLOW == "3m"


def test_the_outlook_runs_monthly_from_the_first_month_of_the_business_to_twelve_months_ahead():
    granularity, starts = flow_buckets("outlook", TODAY, first_month=date(2026, 10, 17))
    assert granularity == "month" and starts[0] == date(2026, 10, 1) and starts[-1] == date(2027, 11, 1)
    assert len(starts) == 14 and date(2026, 11, 1) in starts


def test_the_outlook_without_a_first_month_is_this_month_and_the_twelve_after_it():
    granularity, starts = flow_buckets("outlook", TODAY)
    assert granularity == "month" and starts[0] == date(2026, 11, 1) and len(starts) == 13 and starts[-1] == date(2027, 11, 1)


def test_the_outlook_looks_back_at_most_two_years():
    _, starts = flow_buckets("outlook", TODAY, first_month=date(2015, 1, 1))
    assert starts[0] == date(2024, 12, 1) and len(starts) == 24 + 12
    _, near = flow_buckets("outlook", TODAY, first_month=date(2025, 1, 1))
    assert near[0] == date(2025, 1, 1)
