"""Periods and monthly targets for the forecast: pure date and money arithmetic.

A target is *per month* and a quarter's or year's target is the sum of its months. A month's
target is the income needed per month minus the confirmed other income that arrives in that
month (cash basis, like the sales). Unconfirmed other income is "possible": shown, never
subtracted. Nothing here touches the database.
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


def receipt_dates(first_received_on: date, payments: int) -> list[date]:
    """When a line of other income arrives: the first day, then monthly, `payments` times."""
    if not isinstance(payments, int) or not 1 <= payments <= MAX_RECEIPTS:
        raise ValueError(f"other income has 1 to {MAX_RECEIPTS} payments")
    return [shift_months(first_received_on, step) for step in range(payments)]


def month_targets(monthly_need: Decimal | None, lines: list[dict], months: list[date]) -> dict[date, dict]:
    """{month: {"target", "possible"}} for each month in `months`. `target` is the need minus the
    confirmed other income arriving that month, never below 0 (None with no plan); `possible`
    is the unconfirmed other income arriving that month. A line is {amount_eur,
    first_received_on, payments, confirmed}."""
    confirmed: dict[date, Decimal] = {}
    possible: dict[date, Decimal] = {}
    for line in lines:
        bucket = confirmed if line["confirmed"] else possible
        for received in receipt_dates(line["first_received_on"], line["payments"]):
            month = received.replace(day=1)
            bucket[month] = bucket.get(month, _ZERO) + Decimal(line["amount_eur"])
    result = {}
    for month in months:
        target = None if monthly_need is None else max(_ZERO, Decimal(monthly_need) - confirmed.get(month, _ZERO))
        result[month] = {"target": target, "possible": possible.get(month, _ZERO)}
    return result
