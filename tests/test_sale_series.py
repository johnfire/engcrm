"""Splitting a contract over monthly payments: the amounts and the due dates."""
from datetime import date
from decimal import Decimal

import pytest

from gcrm.sale_series import MAX_MONTHS, due_dates, split_amount


def test_an_even_split_is_exact():
    assert split_amount(Decimal("2400"), 4) == [Decimal("600.00")] * 4


def test_cents_that_do_not_divide_land_on_the_last_payment_so_the_total_is_exact():
    parts = split_amount(Decimal("1000"), 3)
    assert parts == [Decimal("333.33"), Decimal("333.33"), Decimal("333.34")]
    assert sum(parts) == Decimal("1000.00")


@pytest.mark.parametrize("total,months", [("0.07", 5), ("12345.67", 7), ("100", 60), ("1", 2)])
def test_the_parts_always_add_up_and_none_is_zero_or_negative(total, months):
    parts = split_amount(Decimal(total), months)
    assert sum(parts) == Decimal(total).quantize(Decimal("0.01")) and all(p > 0 for p in parts) and len(parts) == months


def test_a_total_too_small_to_split_is_refused():
    with pytest.raises(ValueError):
        split_amount(Decimal("0.03"), 5)       # would need payments of less than one cent


def test_due_dates_are_monthly_from_the_first():
    assert due_dates(date(2027, 2, 1), 4) == [date(2027, 2, 1), date(2027, 3, 1), date(2027, 4, 1), date(2027, 5, 1)]


def test_the_day_of_month_is_kept_and_clipped_in_short_months():
    assert due_dates(date(2027, 1, 31), 4) == [date(2027, 1, 31), date(2027, 2, 28), date(2027, 3, 31), date(2027, 4, 30)]
    assert due_dates(date(2028, 1, 30), 2)[1] == date(2028, 2, 29)      # leap year


def test_the_year_rolls_over():
    assert due_dates(date(2026, 11, 15), 3) == [date(2026, 11, 15), date(2026, 12, 15), date(2027, 1, 15)]


@pytest.mark.parametrize("months", [0, 1, -3, MAX_MONTHS + 1])
def test_only_two_to_the_maximum_months_make_a_schedule(months):
    with pytest.raises(ValueError):
        due_dates(date(2027, 1, 1), months)
