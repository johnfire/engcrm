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


from gcrm.sale_series import contract_from_form  # noqa: E402


def test_the_form_choice_decides_whether_the_amount_is_the_whole_or_per_month():
    assert contract_from_form(Decimal("500"), "one", 9) == (Decimal("500"), 1)
    assert contract_from_form(Decimal("500"), "monthly", 6) == (Decimal("3000"), 6)
    assert contract_from_form(Decimal("2400"), "", 4) == (Decimal("2400"), 4)       # an older form: the total, split
    assert contract_from_form(Decimal("2400"), "", 1) == (Decimal("2400"), 1)


@pytest.mark.parametrize("schedule,months", [("monthly", 1), ("monthly", 61), ("weekly", 3), ("", 0)])
def test_the_form_choice_refuses_nonsense(schedule, months):
    with pytest.raises(ValueError):
        contract_from_form(Decimal("500"), schedule, months)


from gcrm.sale_series import attach_contract_summaries  # noqa: E402


def _payment(part, status, series="abc", amount="500", total=3):
    return {"id": part, "series_id": series, "series_part": part, "series_total": total, "status": status, "amount_eur": amount}


def test_the_first_payment_of_a_contract_carries_its_summary():
    rows = [{"id": 99, "series_id": None, "status": "booked", "amount_eur": "50"},
            _payment(1, "booked"), _payment(2, "booked"), _payment(3, "booked")]
    out = attach_contract_summaries(rows)
    assert "contract" not in out[0] and "contract" not in out[2] and "contract" not in out[3]
    assert out[1]["contract"] == {"payments": 3, "total": Decimal("1500"), "open": 3, "open_status": "booked"}


def test_the_summary_describes_the_payments_still_to_come_not_the_first_one():
    rows = [_payment(1, "collected"), _payment(2, "contracted"), _payment(3, "contracted")]
    assert attach_contract_summaries(rows)[0]["contract"] == {
        "payments": 3, "total": Decimal("1500"), "open": 2, "open_status": "contracted"}


def test_a_fully_received_contract_has_nothing_left_to_move():
    rows = [_payment(1, "collected"), _payment(2, "collected"), _payment(3, "collected")]
    assert attach_contract_summaries(rows)[0]["contract"]["open"] == 0


def test_a_cancelled_remainder_can_be_taken_back_so_it_reports_cancelled():
    rows = [_payment(1, "collected"), _payment(2, "cancelled"), _payment(3, "cancelled")]
    assert attach_contract_summaries(rows)[0]["contract"]["open_status"] == "cancelled"


def test_two_contracts_in_one_list_are_summarised_separately():
    rows = [_payment(1, "booked", series="a"), _payment(2, "booked", series="a", total=2),
            _payment(1, "expected", series="b", amount="100", total=2), _payment(2, "expected", series="b", amount="100", total=2)]
    out = attach_contract_summaries(rows)
    assert out[0]["contract"]["open_status"] == "booked" and out[2]["contract"]["open_status"] == "expected"
    assert out[2]["contract"]["total"] == Decimal("200")


def test_the_summary_is_attached_even_when_the_list_starts_mid_contract():
    rows = [_payment(2, "booked"), _payment(3, "booked")]              # payment 1 is not in this list
    assert attach_contract_summaries(rows)[0]["contract"]["open"] == 2


from gcrm.sale_series import is_month_end, monthly_due_day  # noqa: E402


def test_a_first_payment_on_the_last_day_of_a_month_means_the_last_day_of_every_month():
    assert due_dates(date(2027, 4, 30), 5) == [date(2027, 4, 30), date(2027, 5, 31), date(2027, 6, 30),
                                              date(2027, 7, 31), date(2027, 8, 31)]
    assert due_dates(date(2028, 2, 29), 3) == [date(2028, 2, 29), date(2028, 3, 31), date(2028, 4, 30)]
    assert due_dates(date(2027, 2, 28), 2) == [date(2027, 2, 28), date(2027, 3, 31)]
    assert due_dates(date(2027, 1, 31), 4) == [date(2027, 1, 31), date(2027, 2, 28), date(2027, 3, 31), date(2027, 4, 30)]


def test_any_other_first_day_repeats_on_the_same_day_and_is_clipped_in_short_months():
    assert due_dates(date(2027, 1, 30), 3) == [date(2027, 1, 30), date(2027, 2, 28), date(2027, 3, 30)]
    assert due_dates(date(2027, 5, 15), 3) == [date(2027, 5, 15), date(2027, 6, 15), date(2027, 7, 15)]


def test_monthly_due_day_gives_the_day_a_given_number_of_months_later():
    assert monthly_due_day(date(2027, 4, 30), 0) == date(2027, 4, 30)
    assert monthly_due_day(date(2027, 4, 30), 1) == date(2027, 5, 31)
    assert monthly_due_day(date(2027, 4, 29), 1) == date(2027, 5, 29)
    assert monthly_due_day(date(2026, 12, 31), 2) == date(2027, 2, 28)


@pytest.mark.parametrize("day,expected", [(date(2027, 1, 31), True), (date(2027, 2, 28), True), (date(2028, 2, 29), True),
                                          (date(2028, 2, 28), False), (date(2027, 4, 30), True), (date(2027, 4, 29), False)])
def test_the_last_day_of_a_month_is_recognised(day, expected):
    assert is_month_end(day) is expected


def test_hours_and_a_rate_make_the_amount_and_an_amount_with_hours_gives_the_rate():
    from decimal import Decimal as D

    from gcrm.sale_series import amount_and_hours, rate_of
    assert amount_and_hours(None, D("5"), D("29")) == (D("145.00"), D("5.00"))               # hours x rate
    assert amount_and_hours(D("300"), D("5"), None) == (D("300.00"), D("5.00"))              # an amount, with its hours
    assert amount_and_hours(D("300"), None, None) == (D("300.00"), None)                      # as before: no hours
    assert amount_and_hours(D("300"), D("5"), D("29")) == (D("300.00"), D("5.00"))           # the amount wins; the rate is only a way to type it
    assert rate_of(D("145"), D("5")) == D("29.00") and rate_of(D("100"), D("3")) == D("33.33")
    assert rate_of(D("100"), None) is None and rate_of(D("100"), D("0")) is None


@pytest.mark.parametrize("amount,hours,rate", [(None, None, None), (None, Decimal("5"), None), (None, None, Decimal("29")), (Decimal("0"), Decimal("5"), None),
                                              (Decimal("100"), Decimal("0"), None), (Decimal("100"), Decimal("-2"), None), (None, Decimal("5"), Decimal("0")),
                                              (Decimal("100"), Decimal("100001"), None), (None, Decimal("5"), Decimal("-1")), (Decimal("100"), "lots", None)])
def test_hours_and_amounts_that_make_no_sense_are_refused(amount, hours, rate):
    from gcrm.sale_series import amount_and_hours
    with pytest.raises(ValueError):
        amount_and_hours(amount, hours, rate)


def test_hours_split_over_payments_like_money_and_add_up():
    from decimal import Decimal as D

    from gcrm.sale_series import split_hours
    assert split_hours(D("40"), 3) == [D("13.33"), D("13.33"), D("13.34")]
    assert split_hours(None, 3) == [None, None, None]
    assert sum(split_hours(D("10"), 4)) == D("10.00")
