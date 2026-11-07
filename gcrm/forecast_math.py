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
# (periods back, periods in all) for each view: enough history to see, enough ahead to plan
_WINDOW = {"month": (2, 12), "quarter": (2, 8), "year": (1, 5)}
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


def periods_around(granularity: str, today: date) -> list[date]:
    """The periods to show, oldest first: a little history, this period, and the ones ahead."""
    _check(granularity)
    back, total = _WINDOW[granularity]
    this = period_start(granularity, today)
    first = shift_months(this, -back * _months_long(granularity))
    return [shift_months(first, step * _months_long(granularity)) for step in range(total)]


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
