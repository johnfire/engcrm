"""A contract paid over several months: how the total is split and when each payment is due.

Each payment becomes its own sale row (same contract, own due day, amount and status), so
everything that already works on sales — statuses, statistics, revenue, the backup — works
on payments too. See docs/plans/2026-11-07-payment-schedules.md.
"""
import calendar
from datetime import date
from decimal import ROUND_DOWN, Decimal

MIN_MONTHS = 2
MAX_MONTHS = 60
_CENT = Decimal("0.01")


def check_months(months: int) -> int:
    """The number of monthly payments, or ValueError."""
    if not isinstance(months, int) or not MIN_MONTHS <= months <= MAX_MONTHS:
        raise ValueError(f"a payment schedule has {MIN_MONTHS} to {MAX_MONTHS} monthly payments")
    return months


def split_amount(total: Decimal, months: int) -> list[Decimal]:
    """`total` in `months` payments of whole cents. Every payment but the last is the
    rounded-down share; the last takes what is left, so the parts always add up exactly."""
    check_months(months)
    total = Decimal(total).quantize(_CENT)
    share = (total / months).quantize(_CENT, rounding=ROUND_DOWN)
    if share <= 0:
        raise ValueError("the amount is too small to split into that many payments")
    return [share] * (months - 1) + [total - share * (months - 1)]


def shift_months(first: date, step: int) -> date:
    """The same day of the month `step` months later (clipped to the month's last day)."""
    index = first.month - 1 + step
    year, month = first.year + index // 12, index % 12 + 1
    return date(year, month, min(first.day, calendar.monthrange(year, month)[1]))


def due_dates(first: date, months: int) -> list[date]:
    """The first due day, then the same day of each following month (clipped to the
    month's last day: 31 January, 28 February, 31 March...)."""
    check_months(months)
    return [shift_months(first, step) for step in range(months)]
