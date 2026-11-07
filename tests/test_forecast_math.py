"""Periods and monthly targets for the forecast: pure date and money arithmetic."""
from datetime import date
from decimal import Decimal

import pytest

from gcrm.forecast_math import (
    month_targets,
    months_of,
    period_end,
    period_start,
    periods_around,
    receipt_dates,
)

D = Decimal


def test_period_boundaries():
    assert period_start("month", date(2026, 11, 17)) == date(2026, 11, 1)
    assert period_start("quarter", date(2026, 11, 17)) == date(2026, 10, 1)
    assert period_start("quarter", date(2027, 1, 1)) == date(2027, 1, 1)
    assert period_start("year", date(2026, 11, 17)) == date(2026, 1, 1)
    assert period_end("month", date(2026, 2, 1)) == date(2026, 2, 28)
    assert period_end("month", date(2028, 2, 1)) == date(2028, 2, 29)
    assert period_end("quarter", date(2026, 10, 1)) == date(2026, 12, 31)
    assert period_end("year", date(2026, 1, 1)) == date(2026, 12, 31)


def test_months_inside_a_period():
    assert months_of("month", date(2026, 11, 1)) == [date(2026, 11, 1)]
    assert months_of("quarter", date(2026, 10, 1)) == [date(2026, 10, 1), date(2026, 11, 1), date(2026, 12, 1)]
    assert len(months_of("year", date(2026, 1, 1))) == 12 and months_of("year", date(2026, 1, 1))[-1] == date(2026, 12, 1)


def test_the_periods_shown_run_from_a_little_back_to_well_ahead_and_include_today():
    months = periods_around("month", date(2026, 11, 17))
    assert months[0] == date(2026, 9, 1) and months[-1] == date(2027, 8, 1) and date(2026, 11, 1) in months
    quarters = periods_around("quarter", date(2026, 11, 17))
    assert date(2026, 10, 1) in quarters and quarters == sorted(quarters) and len(quarters) == 8
    years = periods_around("year", date(2026, 11, 17))
    assert years[0] == date(2025, 1, 1) and date(2026, 1, 1) in years and len(years) == 5


def test_unknown_granularity_is_refused():
    with pytest.raises(ValueError):
        period_start("week", date(2026, 11, 1))


def test_receipts_are_monthly_from_the_first_day_and_may_be_a_single_one():
    assert receipt_dates(date(2026, 11, 1), 1) == [date(2026, 11, 1)]
    assert receipt_dates(date(2026, 11, 1), 3) == [date(2026, 11, 1), date(2026, 12, 1), date(2027, 1, 1)]
    assert receipt_dates(date(2027, 1, 31), 2)[1] == date(2027, 2, 28)
    with pytest.raises(ValueError):
        receipt_dates(date(2026, 11, 1), 0)


LINES = [
    {"amount_eur": D("1500"), "first_received_on": date(2026, 11, 1), "payments": 6, "confirmed": True},
    {"amount_eur": D("300"), "first_received_on": date(2027, 5, 1), "payments": 15, "confirmed": False},
]


def test_a_months_target_is_the_need_minus_the_confirmed_income_that_arrives_in_it():
    months = [date(2026, 10, 1), date(2026, 11, 1), date(2027, 4, 1), date(2027, 5, 1)]
    t = month_targets(D("5000"), LINES, months)
    assert t[date(2026, 10, 1)]["target"] == D("5000")                # nothing arrived in October
    assert t[date(2026, 11, 1)]["target"] == D("3500")                # first payment on 1 Nov
    assert t[date(2027, 4, 1)]["target"] == D("3500")                 # sixth and last payment on 1 Apr
    assert t[date(2027, 5, 1)]["target"] == D("5000")                 # the possible follow-on does not count yet
    assert t[date(2027, 5, 1)]["possible"] == D("300") and t[date(2026, 11, 1)]["possible"] == D("0")


def test_confirming_the_follow_on_lowers_the_target_from_then_on():
    confirmed = [LINES[0], {**LINES[1], "confirmed": True}]
    t = month_targets(D("5000"), confirmed, [date(2027, 5, 1), date(2028, 7, 1), date(2028, 8, 1)])
    assert t[date(2027, 5, 1)]["target"] == D("4700")
    assert t[date(2028, 7, 1)]["target"] == D("4700")                 # the fifteenth and last
    assert t[date(2028, 8, 1)]["target"] == D("5000")                 # over


def test_other_income_never_makes_the_target_negative():
    t = month_targets(D("1000"), LINES, [date(2026, 11, 1)])
    assert t[date(2026, 11, 1)]["target"] == D("0")


def test_without_a_plan_there_is_no_target():
    assert month_targets(None, LINES, [date(2026, 11, 1)]) == {date(2026, 11, 1): {"target": None, "possible": D("0")}}
