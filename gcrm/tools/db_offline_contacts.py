"""Workspace-wide monthly counts for contacts recorded outside the CRM."""
from datetime import date

from fastapi import HTTPException

from gcrm.db.connection import db
from gcrm.tools.db_account_lifecycle import get_active_workspace_id
from gcrm.tools.db_audit import log_audit
from gcrm.tools.db_contact_counts import BUSINESS_START, today

MAX_OFFLINE_TOTAL = 1_000_000


def parse_offline_total(month: str, total: str, on: date | None = None) -> tuple[date, int]:
    """Accept a completed/current calendar month's nonnegative whole-number total."""
    try:
        selected = date.fromisoformat(month)
        if not total.isascii() or not total.isdecimal():
            raise ValueError("a whole number is required")
        count = int(total)
    except ValueError as failure:
        raise HTTPException(400, "Enter a valid month and a whole number from 0 to 1000000.") from failure
    if (selected.day != 1 or selected < BUSINESS_START
            or selected > (on or today()).replace(day=1) or count > MAX_OFFLINE_TOTAL):
        raise HTTPException(400, "Choose a month since October 2026, no later than this month, and a count from 0 to 1000000.")
    return selected, count


def get_offline_totals(on: date | None = None) -> dict[str, int]:
    workspace_id = get_active_workspace_id()
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT month_start,total FROM offline_contact_totals "
                       "WHERE workspace_id=%s AND month_start BETWEEN %s AND %s ORDER BY month_start",
                       (workspace_id, BUSINESS_START, (on or today()).replace(day=1)))
        return {row["month_start"].isoformat(): row["total"] for row in cursor.fetchall()}


def save_offline_total(month: date, total: int) -> None:
    workspace_id = get_active_workspace_id()
    with db() as connection:
        connection.cursor().execute(
            "INSERT INTO offline_contact_totals (workspace_id,month_start,total) VALUES (%s,%s,%s) "
            "ON CONFLICT (workspace_id,month_start) DO UPDATE SET total=EXCLUDED.total",
            (workspace_id, month, total))
    log_audit(None, None, "offline_contacts.updated", f"workspace:{workspace_id}/month:{month.isoformat()}",
              f"total:{total}")
