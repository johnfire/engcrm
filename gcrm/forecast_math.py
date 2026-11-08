"""Periods and monthly targets for the forecast: pure date and money arithmetic.

A target is *per month*: the income needed per month, the same every month, and a quarter's or
year's target is the sum of its months. Other income does not lower it: it counts *toward* it, in
the months it *covers* (support paid in arrears for October covers October, though it arrives in
November). Months before the business started have no target. Unconfirmed other income is
"possible": shown, never counted. Nothing here touches the database.
"""
import calendar
from datetime import date, timedelta
from decimal import Decimal

from gcrm.sale_series import shift_months

GRANULARITIES = ("month", "quarter", "year")
MAX_RECEIPTS = 120
WEEKS_PER_MONTH = Decimal(52) / Decimal(12)
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


def monthly_value(hours_per_week: Decimal, rate: Decimal) -> Decimal:
    """Euros a month from `hours_per_week` hours of work a week at `rate` euros an hour (52 weeks a year,
    12 months), in cents."""
    return (Decimal(hours_per_week) * Decimal(rate) * WEEKS_PER_MONTH).quantize(Decimal("0.01"))


def live_bookings(months_from_now: int, paying_months: int | None, delay: int, campaign_months: int | None = None) -> int:
    """How many of the expected new bookings are paying in the month `months_from_now` after this
    one (0 = this month). One booking is made each month from this month on, for `campaign_months`
    months (None: it never stops); each pays from `delay` months after it is booked, for
    `paying_months` months (None: for ever)."""
    newest = months_from_now - delay                        # the latest booking whose first payment is due by now
    if campaign_months is not None:
        newest = min(newest, campaign_months - 1)
    oldest = 0 if paying_months is None else max(0, months_from_now - delay - paying_months + 1)
    return max(0, newest - oldest + 1)


def new_sales_cash(monthly: Decimal | None, paying_months: int | None, delay: int, this_month: date,
                   months: list[date], campaign_months: int | None = None) -> dict[date, Decimal]:
    """{month: € arriving from the expected new bookings} for each month in `months` (all zero without an
    expectation, and before this month). A booking of `monthly` euros a month is made every month
    from `this_month`, for `campaign_months` months (None: it never stops)."""
    cash = {}
    for month in months:
        index = month_index(this_month, month)
        cash[month] = (_ZERO if not monthly or index < 0
                       else Decimal(monthly) * live_bookings(index, paying_months, delay, campaign_months))
    return cash


def month_index(this_month: date, month: date) -> int:
    """How many months `month` is after `this_month` (negative before it)."""
    return (month.year - this_month.year) * 12 + month.month - this_month.month


def new_sales_in_year(monthly: Decimal | None, paying_months: int | None, delay: int, this_month: date,
                      as_of: date, year: int, campaign_months: int | None = None) -> Decimal:
    """The cash the expected new bookings bring in during the calendar `year`, counting the bookings whose
    first payment has started by the month `as_of` (one booking of `monthly` euros a month is made every
    month from `this_month` for `campaign_months` months, None: without end; each pays for `paying_months`
    months, None: for ever, after `delay` months). As the months pass, more bookings have started, so this
    total for the year grows until the campaign ends."""
    if not monthly:
        return _ZERO
    now = month_index(this_month, as_of)
    year_first, year_last = month_index(this_month, date(year, 1, 1)), month_index(this_month, date(year, 12, 1))
    newest = now - delay if campaign_months is None else min(now - delay, campaign_months - 1)
    payments = 0
    for booked in range(0, newest + 1):                           # bookings whose first payment is due by `as_of`
        first = booked + delay
        last = year_last if paying_months is None else min(first + paying_months - 1, year_last)
        payments += max(0, last - max(first, year_first) + 1)
    return Decimal(monthly) * payments


def week_start(day: date) -> date:
    """The Monday of the week `day` falls in."""
    return day - timedelta(days=day.weekday())


def hours_window(work_from: date | None, work_to: date | None, fallback_day: date) -> tuple[date, date]:
    """The days a sale's hours are worked: its work window when it has both ends, otherwise the whole
    calendar month of `fallback_day` (the day its payment is due)."""
    if work_from is not None and work_to is not None:
        return work_from, work_to
    first = fallback_day.replace(day=1)
    return first, first.replace(day=calendar.monthrange(first.year, first.month)[1])


def spread_hours(hours: Decimal, first: date, last: date) -> dict[date, Decimal]:
    """{Monday of the week: hours} for `hours` spread evenly over the days from `first` to `last`
    (inclusive). Raises ValueError when the window ends before it begins."""
    if last < first:
        raise ValueError("the work window ends before it begins")
    days = (last - first).days + 1
    in_week: dict[date, int] = {}
    for offset in range(days):
        monday = week_start(first + timedelta(days=offset))
        in_week[monday] = in_week.get(monday, 0) + 1
    total = Decimal(hours)
    weeks = {monday: (total * count / days).quantize(Decimal("0.0001")) for monday, count in in_week.items()}
    last_monday = max(weeks)
    weeks[last_monday] += total - sum(weeks.values(), _ZERO)          # the rounding left-over lands on the last week
    return weeks
