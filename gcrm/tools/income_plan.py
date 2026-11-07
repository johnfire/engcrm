"""The plan the forecast measures against: income needed per month, and other income.

Everything here runs inside a workspace scope (row-level security), so a workspace only ever
sees and changes its own plan. The figures are the owner's data; none live in code.
"""
from datetime import date
from decimal import Decimal, InvalidOperation

from gcrm.db.connection import db
from gcrm.forecast_math import MAX_RECEIPTS
from gcrm.tools.db_audit import log_audit


def _amount(value, name: str) -> Decimal:
    try:
        number = Decimal(str(value)).quantize(Decimal("0.01"))
    except InvalidOperation:
        raise ValueError(f"{name} must be a number")
    return number


def get_plan() -> dict:
    """{"monthly_need": Decimal | None, "start_month": date | None, "other_income": [lines, by the
    month they start covering]} for this workspace."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT monthly_need, start_month FROM income_plan")
        plan = cur.fetchone()
        cur.execute("SELECT id, label, amount_eur, first_received_on, covers_from, payments, confirmed "
                    "FROM other_income WHERE deleted_at IS NULL ORDER BY covers_from, id")
        lines = [dict(row) for row in cur.fetchall()]
    return {"monthly_need": plan["monthly_need"] if plan else None,
            "start_month": plan["start_month"] if plan else None, "other_income": lines}


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

