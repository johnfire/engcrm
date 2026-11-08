"""The plan the forecast measures against: income needed per month, and other income.

Everything here runs inside a workspace scope (row-level security), so a workspace only ever
sees and changes its own plan. The figures are the owner's data; none live in code.
"""
from datetime import date
from decimal import Decimal, InvalidOperation

from gcrm.db.connection import db
from gcrm.forecast_math import MAX_RECEIPTS, monthly_value
from gcrm.tools.db_audit import log_audit


def _amount(value, name: str) -> Decimal:
    try:
        number = Decimal(str(value)).quantize(Decimal("0.01"))
    except InvalidOperation:
        raise ValueError(f"{name} must be a number")
    return number


def get_plan() -> dict:
    """{"monthly_need": Decimal | None, "start_month": date | None, "expected_new_monthly": Decimal | None,
    "expected_new_months": int | None (None: keeps paying for ever; 1 when nothing is saved),
    "expected_new_delay": int (months from booking to first payment; 1 when nothing is saved),
    "expected_new_campaign": int | None (months the campaign makes new bookings; None: it never stops),
    "expected_new_hours": Decimal | None (hours a week of each booking) and "expected_new_rate" (€ an hour),
    "weekly_capacity": Decimal | None (hours a week that can be worked), "other_income": [lines, by the month they start covering]} for this workspace."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT monthly_need, start_month, expected_new_monthly, expected_new_months, expected_new_delay, expected_new_campaign, expected_new_hours_per_week, expected_new_rate, weekly_capacity FROM income_plan")
        plan = cur.fetchone()
        cur.execute("SELECT id, label, amount_eur, first_received_on, covers_from, payments, confirmed "
                    "FROM other_income WHERE deleted_at IS NULL ORDER BY covers_from, id")
        lines = [dict(row) for row in cur.fetchall()]
    return {"monthly_need": plan["monthly_need"] if plan else None,
            "start_month": plan["start_month"] if plan else None,
            "expected_new_monthly": plan["expected_new_monthly"] if plan else None,
            "expected_new_months": plan["expected_new_months"] if plan else 1,
            "expected_new_delay": plan["expected_new_delay"] if plan else 1,
            "expected_new_campaign": plan["expected_new_campaign"] if plan else None,
            "expected_new_hours": plan["expected_new_hours_per_week"] if plan else None,
            "expected_new_rate": plan["expected_new_rate"] if plan else None,
            "weekly_capacity": plan["weekly_capacity"] if plan else None, "other_income": lines}


def save_monthly_need(amount, start_month: date | None = None) -> None:
    """Set the income needed per month from sales (0 or more) and the first month it applies
    to (any day in the month; None: no limit, every month has a target). Raises ValueError."""
    need = _amount(amount, "the monthly need")
    if need < 0:
        raise ValueError("the monthly need cannot be negative")
    first = start_month.replace(day=1) if start_month else None
    with db() as conn:
        conn.cursor().execute(
            "INSERT INTO income_plan (workspace_id, monthly_need, start_month, updated_at) "
            "VALUES (request_workspace_id(), %s, %s, NOW()) ON CONFLICT (workspace_id) DO UPDATE "
            "SET monthly_need = EXCLUDED.monthly_need, start_month = EXCLUDED.start_month, updated_at = NOW()",
            (need, first))
    log_audit(None, None, "forecast.need_saved", None, "monthly need changed")


MAX_NEW_SALES_MONTHS = 120
MAX_NEW_SALES_DELAY = 24
MAX_HOURS_PER_WEEK, MAX_RATE = 168, 10_000


def save_expected_new_sales(amount, months: int | None = 1, delay: int = 1, campaign: int | None = None,
                            hours=None, rate=None) -> None:
    """Set the euros of new sales expected to be booked each month (0 or more; None clears it) and
    how many months each booking keeps paying its amount (1 = a one-off; None = for ever) and how many
    months after the booking the first payment comes (0 = the same month), and for how many months
    from this one the campaign makes new bookings (None: it never stops). Only
    these change: the monthly need stays as it is. Raises ValueError, changing nothing."""
    value = None if amount is None else _amount(amount, "the expected new sales")
    if value is not None and value < 0:
        raise ValueError("the expected new sales cannot be negative")
    if months is not None and (isinstance(months, bool) or not isinstance(months, int)
                               or not 1 <= months <= MAX_NEW_SALES_MONTHS):
        raise ValueError(f"enter 1 to {MAX_NEW_SALES_MONTHS} months, or i for no end")
    if isinstance(delay, bool) or not isinstance(delay, int) or not 0 <= delay <= MAX_NEW_SALES_DELAY:
        raise ValueError(f"enter 0 to {MAX_NEW_SALES_DELAY} months before the first payment")
    if campaign is not None and (isinstance(campaign, bool) or not isinstance(campaign, int)
                                 or not 1 <= campaign <= MAX_NEW_SALES_MONTHS):
        raise ValueError(f"enter 1 to {MAX_NEW_SALES_MONTHS} months for the campaign, or leave it empty")
    with db() as conn:
        conn.cursor().execute(
            "INSERT INTO income_plan (workspace_id, expected_new_monthly, expected_new_months, expected_new_delay, "
            "expected_new_campaign, expected_new_hours_per_week, expected_new_rate, updated_at) "
            "VALUES (request_workspace_id(), %s, %s, %s, %s, %s, %s, NOW()) ON CONFLICT (workspace_id) DO UPDATE "
            "SET expected_new_monthly = EXCLUDED.expected_new_monthly, "
            "expected_new_months = EXCLUDED.expected_new_months, expected_new_delay = EXCLUDED.expected_new_delay, "
            "expected_new_campaign = EXCLUDED.expected_new_campaign, "
            "expected_new_hours_per_week = EXCLUDED.expected_new_hours_per_week, "
            "expected_new_rate = EXCLUDED.expected_new_rate, updated_at = NOW()",
            (value, months, delay, campaign, hours, rate))
    log_audit(None, None, "forecast.expected_new_saved", None, "expected new sales changed")


def save_expected_new_hours(hours_per_week, rate, months: int | None = 1, delay: int = 1,
                            campaign: int | None = None) -> None:
    """Set the expected new sales as `hours_per_week` hours of work a week at `rate` euros an hour (each
    booking), with the same months, delay and campaign as save_expected_new_sales. Both None clears the
    expectation. Raises ValueError (one without the other, a negative or impossible number), changing nothing."""
    if hours_per_week is None and rate is None:
        save_expected_new_sales(None, months, delay, campaign)
        return
    if hours_per_week is None or rate is None:
        raise ValueError("enter both the hours a week and the rate per hour, or neither")
    hours, euros = _amount(hours_per_week, "the hours a week"), _amount(rate, "the rate per hour")
    if not 0 <= hours <= MAX_HOURS_PER_WEEK:
        raise ValueError(f"enter 0 to {MAX_HOURS_PER_WEEK} hours a week")
    if not 0 <= euros <= MAX_RATE:
        raise ValueError(f"enter a rate of 0 to {MAX_RATE} euros an hour")
    save_expected_new_sales(monthly_value(hours, euros), months, delay, campaign, hours, euros)


def save_weekly_capacity(hours) -> None:
    """Set how many hours a week can be worked (0 to 168; None clears it). Only this changes. Raises ValueError."""
    value = None if hours is None else _amount(hours, "the weekly capacity")
    if value is not None and not 0 <= value <= MAX_HOURS_PER_WEEK:
        raise ValueError(f"enter 0 to {MAX_HOURS_PER_WEEK} hours a week")
    with db() as conn:
        conn.cursor().execute(
            "INSERT INTO income_plan (workspace_id, weekly_capacity, updated_at) VALUES (request_workspace_id(), %s, NOW()) "
            "ON CONFLICT (workspace_id) DO UPDATE SET weekly_capacity = EXCLUDED.weekly_capacity, updated_at = NOW()", (value,))
    log_audit(None, None, "forecast.capacity_saved", None, "weekly capacity changed")


def _checked_line(label: str, amount, first_received_on: date, payments: int,
                  covers_from: date | None) -> tuple[str, Decimal, date]:
    """(label, amount, first covered month) of a line of other income, or ValueError."""
    text = (label or "").strip()[:200]
    value = _amount(amount, "the amount")
    if not text:
        raise ValueError("give this income a name")
    if value <= 0:
        raise ValueError("the amount must be more than 0")
    if not isinstance(payments, int) or not 1 <= payments <= MAX_RECEIPTS:
        raise ValueError(f"enter 1 to {MAX_RECEIPTS} payments")
    return text, value, (covers_from or first_received_on).replace(day=1)


def add_other_income(label: str, amount, first_received_on: date, payments: int, confirmed: bool = True,
                     covers_from: date | None = None) -> int:
    """Add other income: `amount` a month, `payments` times, the first paid on `first_received_on`.
    It covers consecutive months from `covers_from` (default: the month of the first payment;
    set it earlier when the payment is made in arrears). Unconfirmed income is shown as possible
    and does not lower the target. Raises ValueError."""
    text, value, covers = _checked_line(label, amount, first_received_on, payments, covers_from)
    with db() as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO other_income (workspace_id, label, amount_eur, first_received_on, covers_from, "
                    "payments, confirmed) VALUES (request_workspace_id(), %s, %s, %s, %s, %s, %s) RETURNING id",
                    (text, value, first_received_on, covers, payments, bool(confirmed)))
        line_id = cur.fetchone()["id"]
    log_audit(None, None, "forecast.other_income_added", f"other_income:{line_id}", f"{payments} payments")
    return line_id


def update_other_income(line_id: int, label: str, amount, first_received_on: date, payments: int,
                        confirmed: bool, covers_from: date | None = None) -> bool:
    """Change a line of other income. False when this workspace has no such line; ValueError
    for input that add_other_income would refuse (checked first, so a refused edit changes nothing)."""
    text, value, covers = _checked_line(label, amount, first_received_on, payments, covers_from)
    with db() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE other_income SET label = %s, amount_eur = %s, first_received_on = %s, covers_from = %s, "
                    "payments = %s, confirmed = %s WHERE id = %s AND deleted_at IS NULL "
                    "AND workspace_id = request_workspace_id()",
                    (text, value, first_received_on, covers, payments, bool(confirmed), line_id))
        changed = cur.rowcount > 0
    if changed:
        log_audit(None, None, "forecast.other_income_edited", f"other_income:{line_id}", None)
    return changed


def set_other_income_confirmed(line_id: int, confirmed: bool) -> bool:
    """Confirm (or un-confirm) a line of other income. False when this workspace has no such line."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE other_income SET confirmed = %s WHERE id = %s AND deleted_at IS NULL "
                    "AND workspace_id = request_workspace_id()", (bool(confirmed), line_id))
        changed = cur.rowcount > 0
    if changed:
        log_audit(None, None, "forecast.other_income_confirmed", f"other_income:{line_id}", str(bool(confirmed)))
    return changed


def delete_other_income(line_id: int) -> bool:
    """Remove a line of other income (soft delete). False when this workspace has no such line."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE other_income SET deleted_at = NOW() WHERE id = %s AND deleted_at IS NULL "
                    "AND workspace_id = request_workspace_id()", (line_id,))
        deleted = cur.rowcount > 0
    if deleted:
        log_audit(None, None, "forecast.other_income_deleted", f"other_income:{line_id}", None)
    return deleted

