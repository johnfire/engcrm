"""A contract paid over several months: how the total is split and when each payment is due.

Each payment becomes its own sale row (same contract, own due day, amount and status), so
everything that already works on sales — statuses, statistics, revenue, the backup — works
on payments too. See docs/plans/2026-11-07-payment-schedules.md.
"""
import calendar
from datetime import date
from decimal import ROUND_DOWN, Decimal, InvalidOperation

MIN_MONTHS = 2
MAX_MONTHS = 60
_CENT = Decimal("0.01")
MAX_SALE_HOURS = Decimal(100000)


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


def is_month_end(day: date) -> bool:
    """Whether `day` is the last day of its month."""
    return day.day == calendar.monthrange(day.year, day.month)[1]


def monthly_due_day(first: date, step: int) -> date:
    """The due day of the payment `step` months after one due on `first`: the same day of the month
    (clipped in a short month: 31 January, 28 February), or, when `first` is the last day of its month,
    the last day of each month (30 April, 31 May, 30 June)."""
    later = shift_months(first, step)
    if is_month_end(first):
        return later.replace(day=calendar.monthrange(later.year, later.month)[1])
    return later


def due_dates(first: date, months: int) -> list[date]:
    """The first due day, then one a month on from it (see monthly_due_day): the same day of the month, or
    the last day of each month when the first is the last day of its month."""
    check_months(months)
    return [monthly_due_day(first, step) for step in range(months)]


def contract_from_form(amount: Decimal, schedule: str, months: int) -> tuple[Decimal, int]:
    """(total, number of payments) for what the Sales form sent. "one": a single payment of
    the amount (the months box is ignored). "monthly": the amount is *per month*, so the
    contract is amount × months, in 2 to 60 payments. Blank (an older form): the amount is
    the total, split over `months` payments (1 = a single payment). Raises ValueError."""
    if schedule == "one":
        return amount, 1
    if schedule == "monthly":
        return amount * check_months(months), months
    if schedule == "":
        return amount, 1 if months == 1 else check_months(months)
    raise ValueError("choose a one-time payment or monthly payments")


def attach_contract_summaries(sales: list[dict]) -> list[dict]:
    """Give the first payment of each contract in `sales` a `contract` summary for the screen:
    {payments, total (cancelled payments left out), open, open_status}. `open` counts the
    payments not yet received and `open_status` is the status they are in (that of the first
    of them), so the whole-contract control describes what is still to come rather than
    copying a payment that was already received. Mutates and returns the list."""
    contracts: dict[str, list[dict]] = {}
    for sale in sales:
        if sale.get("series_id"):
            contracts.setdefault(sale["series_id"], []).append(sale)
    for payments in contracts.values():
        payments.sort(key=lambda sale: sale["series_part"])
        still_open = [sale for sale in payments if sale["status"] != "collected"]
        payments[0]["contract"] = {
            "payments": payments[0].get("series_total") or len(payments),
            "total": sum((Decimal(str(sale["amount_eur"])) for sale in payments if sale["status"] != "cancelled"), Decimal("0")),
            "open": len(still_open),
            "open_status": still_open[0]["status"] if still_open else None,
        }
    return sales


def _number(value, name: str) -> Decimal:
    try:
        return Decimal(str(value)).quantize(_CENT)
    except InvalidOperation:
        raise ValueError(f"{name} must be a number")


def amount_and_hours(amount, hours, rate) -> tuple[Decimal, Decimal | None]:
    """(amount, hours) for a sale from what was typed: an amount (with or without hours), or hours and a
    rate per hour, whose product is the amount. When the amount is given the rate is not needed (it is
    worked out again as amount / hours). Raises ValueError for anything missing, zero or negative."""
    worked = None if hours is None else _number(hours, "the hours")
    if worked is not None and not 0 < worked <= MAX_SALE_HOURS:
        raise ValueError("the hours must be more than 0")
    if amount is None:
        if worked is None or rate is None:
            raise ValueError("give an amount, or the hours and a rate per hour")
        per_hour = _number(rate, "the rate per hour")
        if per_hour <= 0:
            raise ValueError("the rate per hour must be more than 0")
        return (worked * per_hour).quantize(_CENT), worked
    money = _number(amount, "the amount")
    if money <= 0:
        raise ValueError("amount must be more than 0")
    return money, worked


def rate_of(amount, hours) -> Decimal | None:
    """The euros per hour of a sale, or None without hours."""
    if not hours or Decimal(str(hours)) <= 0:
        return None
    return (Decimal(str(amount)) / Decimal(str(hours))).quantize(_CENT)


def split_hours(total: Decimal | None, months: int) -> list[Decimal | None]:
    """The hours of a contract over its payments, split like the money; None stays None."""
    if total is None:
        return [None] * months
    return split_amount(total, months)


def contract_hours(hours: Decimal | None, schedule: str, months: int) -> Decimal | None:
    """The hours of a whole contract: typed per month for a "monthly" schedule, so times the months."""
    return hours * months if hours is not None and schedule == "monthly" else hours


def typed_number(text: str) -> Decimal | None:
    """A number typed in a form field, with a comma or a point; None when the field is blank.
    Raises InvalidOperation for text that is no number."""
    cleaned = (text or "").replace(",", ".").strip()
    return Decimal(cleaned) if cleaned else None
