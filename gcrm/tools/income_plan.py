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
    """{"monthly_need": Decimal | None, "other_income": [lines, oldest first]} for this workspace."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT monthly_need FROM income_plan")
        plan = cur.fetchone()
        cur.execute("SELECT id, label, amount_eur, first_received_on, payments, confirmed FROM other_income "
                    "WHERE deleted_at IS NULL ORDER BY first_received_on, id")
        lines = [dict(row) for row in cur.fetchall()]
    return {"monthly_need": plan["monthly_need"] if plan else None, "other_income": lines}


def save_monthly_need(amount) -> None:
    """Set the income needed per month from sales (0 or more). Raises ValueError."""
    need = _amount(amount, "the monthly need")
    if need < 0:
        raise ValueError("the monthly need cannot be negative")
    with db() as conn:
        conn.cursor().execute(
            "INSERT INTO income_plan (workspace_id, monthly_need, updated_at) VALUES (request_workspace_id(), %s, NOW()) "
            "ON CONFLICT (workspace_id) DO UPDATE SET monthly_need = EXCLUDED.monthly_need, updated_at = NOW()",
            (need,))
    log_audit(None, None, "forecast.need_saved", None, "monthly need changed")


def add_other_income(label: str, amount, first_received_on: date, payments: int, confirmed: bool = True) -> int:
    """Add other income: `amount` arriving on `first_received_on`, then monthly, `payments` times.
    Unconfirmed income is shown as possible and does not lower the target. Raises ValueError."""
    text = (label or "").strip()[:200]
    value = _amount(amount, "the amount")
    if not text:
        raise ValueError("give this income a name")
    if value <= 0:
        raise ValueError("the amount must be more than 0")
    if not isinstance(payments, int) or not 1 <= payments <= MAX_RECEIPTS:
        raise ValueError(f"enter 1 to {MAX_RECEIPTS} payments")
    with db() as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO other_income (workspace_id, label, amount_eur, first_received_on, payments, confirmed) "
                    "VALUES (request_workspace_id(), %s, %s, %s, %s, %s) RETURNING id",
                    (text, value, first_received_on, payments, bool(confirmed)))
        line_id = cur.fetchone()["id"]
    log_audit(None, None, "forecast.other_income_added", f"other_income:{line_id}", f"{payments} payments")
    return line_id


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

