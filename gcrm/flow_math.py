"""Windows and pace for the contract-flow graphs: pure date and money arithmetic.

Four ranges: the last 3 months (13 weeks), the last 12 months, the whole business (from its first
month; by year once that is more than four years), and the outlook (monthly, from the first month,
at most two years back, to twelve months ahead). Each is cut into buckets: a week (Monday to
Sunday), a month or a year. The target and the other income are spread evenly over the
days of each month, so a graph by the week can compare money in with a smooth pace. Nothing here
touches the database.
"""
import calendar
from datetime import date, timedelta
from decimal import Decimal

from gcrm.forecast_math import month_targets
from gcrm.sale_series import shift_months

FLOW_RANGES = ("3m", "year", "all", "outlook")
DEFAULT_FLOW = "3m"      # weekly: shows the pick-up of a young business best
WEEKS_SHOWN = 13
MONTHS_SHOWN = 12
MONTHS_BEFORE_YEARS = 48
OUTLOOK_HISTORY_MONTHS = 24     # at most, counting this month
OUTLOOK_MONTHS_AHEAD = 12
_ZERO = Decimal("0")


def bucket_start(granularity: str, day: date) -> date:
    """The first day of the week (Monday), month or year `day` falls in."""
    if granularity == "week":
        return day - timedelta(days=day.weekday())
    if granularity == "month":
        return day.replace(day=1)
    if granularity == "year":
        return date(day.year, 1, 1)
    raise ValueError(f"unknown bucket size {granularity!r}")


def _next_start(granularity: str, start: date) -> date:
    if granularity == "week":
        return start + timedelta(weeks=1)
    return shift_months(start, 12 if granularity == "year" else 1)


def bucket_end(granularity: str, start: date) -> date:
    """The last day (inclusive) of the bucket that begins on `start`."""
    return _next_start(granularity, start) - timedelta(days=1)


def flow_buckets(range_key: str, today: date, first_month: date | None = None) -> tuple[str, list[date]]:
    """(bucket size, the first day of each bucket, oldest first) for a range. `first_month` is the
    first month of the business, for "all" (default: this month)."""
    if range_key == "3m":
        this = bucket_start("week", today)
        return "week", [this - timedelta(weeks=n) for n in range(WEEKS_SHOWN - 1, -1, -1)]
    this_month = today.replace(day=1)
    if range_key == "year":
        return "month", [shift_months(this_month, -n) for n in range(MONTHS_SHOWN - 1, -1, -1)]
    if range_key == "outlook":
        first = min(first_month.replace(day=1), this_month) if first_month else this_month
        first = max(first, shift_months(this_month, 1 - OUTLOOK_HISTORY_MONTHS))
        last = shift_months(this_month, OUTLOOK_MONTHS_AHEAD)
        months = (last.year - first.year) * 12 + last.month - first.month + 1
        return "month", [shift_months(first, n) for n in range(months)]
    if range_key != "all":
        raise ValueError(f"unknown range {range_key!r}")
    first = min(first_month.replace(day=1), this_month) if first_month else this_month
    months = (this_month.year - first.year) * 12 + this_month.month - first.month + 1
    if months > MONTHS_BEFORE_YEARS:
        return "year", [date(year, 1, 1) for year in range(first.year, today.year + 1)]
    return "month", [shift_months(first, n) for n in range(months)]


def daily_pace(monthly_need: Decimal | None, lines: list[dict], start_month: date | None,
               first_day: date, last_day: date) -> dict[date, dict]:
    """{day: {"target", "covered"}} for each day from `first_day` to `last_day`: that month's target
    and confirmed other income divided evenly over the days of the month. A day before the first month
    of the business has no target; with no monthly need entered the target is 0."""
    days = [first_day + timedelta(days=n) for n in range((last_day - first_day).days + 1)]
    months = sorted({day.replace(day=1) for day in days})
    monthly = month_targets(monthly_need, lines, months, start_month)
    pace = {}
    for day in days:
        month = day.replace(day=1)
        length = calendar.monthrange(day.year, day.month)[1]
        target = monthly[month]["target"]
        pace[day] = {"target": (target or _ZERO) / length, "covered": monthly[month]["covered"] / length}
    return pace
