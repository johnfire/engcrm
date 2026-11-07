"""Periods and monthly targets for the forecast: pure date and money arithmetic."""
from datetime import date
from decimal import Decimal

import pytest

from gcrm.forecast_math import (
    coverage_months,
    month_targets,
    months_of,
    period_end,
    period_start,
    periods_around,
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


def test_other_income_covers_consecutive_months_from_the_first_one_it_covers():
    assert coverage_months(date(2026, 10, 1), 1) == [date(2026, 10, 1)]
    assert coverage_months(date(2026, 10, 1), 3) == [date(2026, 10, 1), date(2026, 11, 1), date(2026, 12, 1)]
    assert coverage_months(date(2026, 11, 17), 2) == [date(2026, 11, 1), date(2026, 12, 1)]     # any day in the month will do
    assert coverage_months(date(2026, 11, 1), 3)[-1] == date(2027, 1, 1)
    with pytest.raises(ValueError):
        coverage_months(date(2026, 10, 1), 0)


# Support of 1500 a month covering October to March (it is paid a month later, but it covers those
# months), and a possible follow-on of 300 a month from April.
LINES = [
    {"amount_eur": D("1500"), "covers_from": date(2026, 10, 1), "payments": 6, "confirmed": True},
    {"amount_eur": D("300"), "covers_from": date(2027, 4, 1), "payments": 15, "confirmed": False},
]
OCT = date(2026, 10, 1)


def test_a_months_target_is_the_need_minus_the_confirmed_income_that_covers_it():
    months = [date(2026, 10, 1), date(2026, 11, 1), date(2027, 3, 1), date(2027, 4, 1)]
    t = month_targets(D("5000"), LINES, months)
    assert t[date(2026, 10, 1)] == {"target": D("3500"), "possible": D("0"), "covered": D("1500")}
    assert t[date(2026, 11, 1)]["target"] == D("3500")
    assert t[date(2027, 3, 1)]["target"] == D("3500")                 # the sixth and last month covered
    assert t[date(2027, 4, 1)] == {"target": D("5000"), "possible": D("300"), "covered": D("0")}   # follow-on not confirmed


def test_confirming_the_follow_on_lowers_the_target_from_then_on():
    confirmed = [LINES[0], {**LINES[1], "confirmed": True}]
    t = month_targets(D("5000"), confirmed, [date(2027, 4, 1), date(2028, 6, 1), date(2028, 7, 1)])
    assert t[date(2027, 4, 1)]["target"] == D("4700")
    assert t[date(2028, 6, 1)]["target"] == D("4700")                 # the fifteenth and last month
    assert t[date(2028, 7, 1)]["target"] == D("5000")                 # over


def test_nothing_before_the_first_month_of_the_business_has_a_target():
    t = month_targets(D("5000"), LINES, [date(2026, 9, 1), OCT, date(2026, 11, 1)], start_month=OCT)
    assert t[date(2026, 9, 1)]["target"] is None
    assert t[OCT]["target"] == D("3500") and t[date(2026, 11, 1)]["target"] == D("3500")
    assert t[date(2026, 9, 1)]["covered"] == D("0")


def test_the_first_month_may_be_given_as_any_day_of_it():
    t = month_targets(D("5000"), [], [date(2026, 9, 1), OCT], start_month=date(2026, 10, 17))
    assert t[date(2026, 9, 1)]["target"] is None and t[OCT]["target"] == D("5000")


def test_other_income_never_makes_the_target_negative():
    t = month_targets(D("1000"), LINES, [OCT])
    assert t[OCT]["target"] == D("0")


def test_without_a_need_there_is_no_target_but_the_income_is_still_reported():
    assert month_targets(None, LINES, [OCT]) == {OCT: {"target": None, "possible": D("0"), "covered": D("1500")}}
