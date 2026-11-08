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


def test_months_run_from_the_start_of_this_year_to_the_end_of_next_year():
    months = periods_around("month", date(2026, 11, 17))
    assert months[0] == date(2026, 1, 1) and months[-1] == date(2027, 12, 1) and len(months) == 24
    assert months == sorted(months) and date(2026, 11, 1) in months


def test_a_business_that_started_this_year_shows_only_its_own_months_of_this_year_then_all_of_next_year():
    months = periods_around("month", date(2026, 11, 17), first_month=date(2026, 10, 1))
    assert months[0] == date(2026, 10, 1) and months[-1] == date(2027, 12, 1) and len(months) == 15
    assert months[:3] == [date(2026, 10, 1), date(2026, 11, 1), date(2026, 12, 1)]


def test_a_business_older_than_this_year_still_starts_at_january():
    months = periods_around("month", date(2027, 3, 10), first_month=date(2026, 10, 1))
    assert months[0] == date(2027, 1, 1) and months[-1] == date(2028, 12, 1) and len(months) == 24


def test_quarters_follow_the_same_window():
    assert periods_around("quarter", date(2026, 11, 17)) == [
        date(2026, 1, 1), date(2026, 4, 1), date(2026, 7, 1), date(2026, 10, 1),
        date(2027, 1, 1), date(2027, 4, 1), date(2027, 7, 1), date(2027, 10, 1)]
    assert periods_around("quarter", date(2026, 11, 17), first_month=date(2026, 10, 1)) == [
        date(2026, 10, 1), date(2027, 1, 1), date(2027, 4, 1), date(2027, 7, 1), date(2027, 10, 1)]


def test_years_are_this_year_and_next():
    assert periods_around("year", date(2026, 11, 17)) == [date(2026, 1, 1), date(2027, 1, 1)]
    assert periods_around("year", date(2027, 3, 10), first_month=date(2026, 10, 1)) == [date(2027, 1, 1), date(2028, 1, 1)]


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


def test_a_months_target_is_the_plain_need_and_the_income_covering_it_is_reported_beside_it():
    months = [date(2026, 10, 1), date(2026, 11, 1), date(2027, 3, 1), date(2027, 4, 1)]
    t = month_targets(D("5000"), LINES, months)
    assert t[date(2026, 10, 1)] == {"target": D("5000"), "possible": D("0"), "covered": D("1500")}
    assert t[date(2026, 11, 1)] == {"target": D("5000"), "possible": D("0"), "covered": D("1500")}
    assert t[date(2027, 3, 1)]["covered"] == D("1500")                # the sixth and last month covered
    assert t[date(2027, 4, 1)] == {"target": D("5000"), "possible": D("300"), "covered": D("0")}   # follow-on not confirmed


def test_confirming_the_follow_on_makes_it_count_from_then_on():
    confirmed = [LINES[0], {**LINES[1], "confirmed": True}]
    t = month_targets(D("5000"), confirmed, [date(2027, 4, 1), date(2028, 6, 1), date(2028, 7, 1)])
    assert (t[date(2027, 4, 1)]["covered"], t[date(2027, 4, 1)]["possible"]) == (D("300"), D("0"))
    assert t[date(2028, 6, 1)]["covered"] == D("300")                 # the fifteenth and last month
    assert t[date(2028, 7, 1)]["covered"] == D("0")                   # over
    assert {m["target"] for m in t.values()} == {D("5000")}           # the target never moves


def test_nothing_before_the_first_month_of_the_business_has_a_target():
    t = month_targets(D("5000"), LINES, [date(2026, 9, 1), OCT, date(2026, 11, 1)], start_month=OCT)
    assert t[date(2026, 9, 1)]["target"] is None
    assert t[OCT]["target"] == D("5000") and t[date(2026, 11, 1)]["target"] == D("5000")
    assert t[date(2026, 9, 1)]["covered"] == D("0")


def test_the_first_month_may_be_given_as_any_day_of_it():
    t = month_targets(D("5000"), [], [date(2026, 9, 1), OCT], start_month=date(2026, 10, 17))
    assert t[date(2026, 9, 1)]["target"] is None and t[OCT]["target"] == D("5000")


def test_other_income_bigger_than_the_need_does_not_change_the_target():
    t = month_targets(D("1000"), LINES, [OCT])
    assert t[OCT] == {"target": D("1000"), "possible": D("0"), "covered": D("1500")}


def test_without_a_need_there_is_no_target_but_the_income_is_still_reported():
    assert month_targets(None, LINES, [OCT]) == {OCT: {"target": None, "possible": D("0"), "covered": D("1500")}}


def test_how_many_expected_bookings_are_paying_in_a_month():
    from gcrm.forecast_math import live_bookings
    assert [live_bookings(j, None, 1) for j in range(5)] == [0, 1, 2, 3, 4]            # for ever, first payment a month on
    assert [live_bookings(j, 3, 1) for j in range(6)] == [0, 1, 2, 3, 3, 3]            # each pays three months
    assert [live_bookings(j, 1, 0) for j in range(3)] == [1, 1, 1]                      # a one-off paid the month it is booked
    assert [live_bookings(j, 2, 2) for j in range(5)] == [0, 0, 1, 2, 2]


def test_cash_from_the_expected_new_sales_by_month_never_comes_before_this_month():
    from decimal import Decimal

    from gcrm.forecast_math import new_sales_cash
    this = date(2026, 11, 1)
    months = [date(2026, 10, 1), date(2026, 11, 1), date(2026, 12, 1), date(2027, 1, 1)]
    assert new_sales_cash(Decimal("1000"), None, 1, this, months) == {
        date(2026, 10, 1): 0, date(2026, 11, 1): 0, date(2026, 12, 1): Decimal("1000"), date(2027, 1, 1): Decimal("2000")}
    assert all(v == 0 for v in new_sales_cash(None, None, 1, this, months).values())


def test_the_calendar_year_total_of_the_expected_new_sales_as_of_each_month():
    from decimal import Decimal

    from gcrm.forecast_math import new_sales_in_year
    this = date(2026, 11, 1)

    def at(month, year=2027, paying=None, delay=1):
        return new_sales_in_year(Decimal("1000"), paying, delay, this, month, year)
    # Nov and Dec bookings (paid for ever, from a month on) are paying by January: 12 + 12 payments in 2027
    assert at(date(2027, 1, 1)) == Decimal("24000")
    assert at(date(2027, 2, 1)) == Decimal("35000")                                    # the January booking adds 11 more
    assert at(date(2027, 3, 1)) == Decimal("45000")                                    # February's adds 10
    assert at(date(2026, 12, 1), year=2027) == Decimal("12000")                         # only November's has started: 12 payments
    assert at(date(2027, 1, 1), paying=1) == Decimal("1000")                            # one-offs: only December's lands in 2027
    assert at(date(2027, 1, 1), delay=0) == Decimal("36000")                            # Nov, Dec, Jan bookings, 12 payments each
    assert new_sales_in_year(None, None, 1, this, date(2027, 1, 1), 2027) == 0
    assert new_sales_in_year(Decimal("1000"), None, 1, this, date(2027, 1, 1), 2026) == Decimal("1000")   # Dec 2026: November's first payment


def test_a_campaign_that_stops_adds_no_more_bookings_after_its_last_month():
    from gcrm.forecast_math import live_bookings
    # November to February = 4 months; for ever, paid from a month on: it climbs to 4 and stays there
    assert [live_bookings(j, None, 1, 4) for j in range(8)] == [0, 1, 2, 3, 4, 4, 4, 4]
    # each booking pays 2 months: the last booking (made in month 3) pays in months 4 and 5, then nothing
    assert [live_bookings(j, 2, 1, 4) for j in range(8)] == [0, 1, 2, 2, 2, 1, 0, 0]
    assert [live_bookings(j, None, 1, None) for j in range(5)] == [0, 1, 2, 3, 4]               # no end: as before
    assert [live_bookings(j, 1, 0, 3) for j in range(5)] == [1, 1, 1, 0, 0]                       # one-offs, three months


def test_cash_and_the_year_total_follow_a_campaign_that_stops():
    from decimal import Decimal

    from gcrm.forecast_math import new_sales_cash, new_sales_in_year
    this = date(2026, 11, 1)
    months = [date(2026, 11, 1), date(2026, 12, 1), date(2027, 1, 1), date(2027, 2, 1), date(2027, 3, 1), date(2027, 4, 1)]
    cash = new_sales_cash(Decimal("1000"), None, 1, this, months, 4)
    assert list(cash.values()) == [0, 1000, 2000, 3000, 4000, 4000]
    # Nov..Feb bookings, paid for ever from a month on: their first payments are Dec, Jan, Feb, Mar,
    # so in 2027 they pay 12 + 12 + 11 + 10 months
    assert new_sales_in_year(Decimal("1000"), None, 1, this, date(2027, 12, 1), 2027, 4) == Decimal("45000")
    assert new_sales_in_year(Decimal("1000"), None, 1, this, date(2027, 12, 1), 2027, None) == Decimal("90000")   # no end: 24 + (11+...+1)
    assert new_sales_in_year(Decimal("1000"), None, 1, this, date(2027, 1, 1), 2027, 4) == Decimal("24000")      # as of January: same as before
