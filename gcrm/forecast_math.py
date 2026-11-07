"""Periods and monthly targets for the forecast: pure date and money arithmetic.

A target is *per month*: the income needed per month, the same every month, and a quarter's or
year's target is the sum of its months. Other income does not lower it: it counts *toward* it, in
the months it *covers* (support paid in arrears for October covers October, though it arrives in
November). Months before the business started have no target. Unconfirmed other income is
"possible": shown, never counted. Nothing here touches the database.
"""
import calendar
from datetime import date
from decimal import Decimal

from gcrm.sale_series import shift_months

GRANULARITIES = ("month", "quarter", "year")
MAX_RECEIPTS = 120
_ZERO = Decimal("0")


def _check(granularity: str) -> None:
    if granularity not in GRANULARITIES:
        raise ValueError(f"unknown granularity {granularity!r}")


def period_start(granularity: str, day: date) -> date:
    """The first day of the month, quarter or year `day` falls in."""
    _check(granularity)
    if granularity == "month":
        return day.replace(day=1)
    if granularity == "quarter":
        return date(day.year, (day.month - 1) // 3 * 3 + 1, 1)
    return date(day.year, 1, 1)


def _months_long(granularity: str) -> int:
    return {"month": 1, "quarter": 3, "year": 12}[granularity]


def period_end(granularity: str, start: date) -> date:
    """The last day (inclusive) of the period that begins on `start`."""
    _check(granularity)
    last = shift_months(start.replace(day=1), _months_long(granularity) - 1)
    return last.replace(day=calendar.monthrange(last.year, last.month)[1])


def months_of(granularity: str, start: date) -> list[date]:
    """The first day of each month in the period that begins on `start`."""
    _check(granularity)
    return [shift_months(start, step) for step in range(_months_long(granularity))]


def periods_around(granularity: str, today: date, first_month: date | None = None) -> list[date]:
    """The periods to show, oldest first: this year from its first month in business (January,
    or `first_month` when the business started later this year) through the end of next year.
    Years: this year and next."""
    _check(granularity)
    this_year = date(today.year, 1, 1)
    first = this_year if first_month is None else max(this_year, first_month.replace(day=1))
    end_of_window = date(today.year + 1, 12, 1)
    if granularity == "year":
        return [this_year, date(today.year + 1, 1, 1)]
    start = period_start(granularity, first)
    step = _months_long(granularity)
    periods = []
    while start <= end_of_window:
        periods.append(start)
        start = shift_months(start, step)
    return periods


def coverage_months(covers_from: date, payments: int) -> list[date]:
    """The months a line of other income covers: `payments` consecutive months, the first being
    the month of `covers_from` (any day in it will do)."""
    if not isinstance(payments, int) or not 1 <= payments <= MAX_RECEIPTS:
        raise ValueError(f"other income has 1 to {MAX_RECEIPTS} payments")
    first = covers_from.replace(day=1)
    return [shift_months(first, step) for step in range(payments)]


def month_targets(monthly_need: Decimal | None, lines: list[dict], months: list[date],
                  start_month: date | None = None) -> dict[date, dict]:
    """{month: {"target", "possible", "covered"}} for each month in `months`. `covered` is the
    confirmed other income covering that month (it counts toward the target) and `possible` the
    unconfirmed. `target` is the monthly need itself, the same every month; it is None with no need
    entered, and for months before `start_month`. A line is {amount_eur, covers_from, payments,
    confirmed}."""
    confirmed: dict[date, Decimal] = {}
    possible: dict[date, Decimal] = {}
    for line in lines:
        bucket = confirmed if line["confirmed"] else possible
        for month in coverage_months(line["covers_from"], line["payments"]):
            bucket[month] = bucket.get(month, _ZERO) + Decimal(line["amount_eur"])
    first = start_month.replace(day=1) if start_month else None
    result = {}
    for month in months:
        covered = confirmed.get(month, _ZERO)
        in_business = first is None or month >= first
        target = None if (monthly_need is None or not in_business) else Decimal(monthly_need)
        result[month] = {"target": target, "possible": possible.get(month, _ZERO), "covered": covered}
    return result
