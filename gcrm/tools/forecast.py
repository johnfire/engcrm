"""What is coming in, and when: money by month, quarter or year against a target.

Each sale row (a one-off, or one payment of a contract) sits in the month of its due day
(`expected_on`), or of the day it was received (`collected_on`) once collected. Cancelled
money is left out. Money with no due day is reported apart as "undated" instead of vanishing.

  collected   received      contracted  a written contract exists   booked    agreed
  expected    a hope        secured = collected + contracted + booked
  total = secured + expected

Targets come from the income plan (gcrm/tools/income_plan.py): per month, summed for a
quarter or year. Nothing here weights money by likelihood: it is what it is.
"""
from datetime import date
from decimal import Decimal

from gcrm.db.connection import db
from gcrm.forecast_math import (
    month_targets,
    months_of,
    period_end,
    period_start,
    periods_around,
    shift_months,
)
from gcrm.sale_status import SALE_STATUSES
from gcrm.tools.db_deals import offer_id_sql
from gcrm.tools.income_plan import get_plan

_ZERO = Decimal("0")
# The tiles above the table, in order: (key, granularity, how many periods after the current one).
TILES = (("this_month", "month", 0), ("next_month", "month", 1), ("month_after", "month", 2),
         ("this_quarter", "quarter", 0), ("next_quarter", "quarter", 1),
         ("this_year", "year", 0), ("next_year", "year", 1))
_MONTHS_LONG = {"month": 1, "quarter": 3, "year": 12}
_MONEY = tuple(status for status in SALE_STATUSES if status != "cancelled")


def _blank() -> dict:
    return {status: _ZERO for status in _MONEY}


def _monthly_money(workspace_id: int, first: date, last: date, offer: str | None) -> tuple[dict, dict, int]:
    """({month: {status: €}}, undated {status: €}, undated count) for the live sales of the
    workspace, organizations' and people's alike, between `first` and `last` inclusive."""
    only = f" AND dl.offer_id = {offer_id_sql('%s', offer)}" if offer else ""
    extra = [workspace_id] if offer else []
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT date_trunc('month', due)::date AS month, status, SUM(amount_eur) AS eur, COUNT(*) AS n FROM ("
            "  SELECT s.status, s.amount_eur, CASE WHEN s.status = 'collected' THEN s.collected_on ELSE s.expected_on END AS due"
            "    FROM sales s JOIN deals dl ON dl.id = s.deal_id AND dl.deleted_at IS NULL"
            "    LEFT JOIN contacts c ON c.id = dl.contact_id LEFT JOIN people p ON p.id = dl.person_id"
            "   WHERE s.workspace_id = %s AND s.deleted_at IS NULL AND s.status <> 'cancelled'"
            f"     AND COALESCE(c.deleted_at, p.deleted_at) IS NULL{only}"
            ") x WHERE due IS NULL OR due BETWEEN %s AND %s GROUP BY 1, 2",
            [workspace_id, *extra, first, last],
        )
        rows = cur.fetchall()
    months: dict[date, dict] = {}
    undated, undated_count = _blank(), 0
    for row in rows:
        if row["month"] is None:
            undated[row["status"]] += Decimal(row["eur"])
            undated_count += row["n"]
        else:
            months.setdefault(row["month"], _blank())[row["status"]] += Decimal(row["eur"])
    return months, undated, undated_count


def _period(granularity: str, start: date, money: dict, targets: dict, has_plan: bool) -> dict:
    months = months_of(granularity, start)
    sums = _blank()
    for month in months:
        for status, euros in money.get(month, {}).items():
            sums[status] += euros
    secured = sums["collected"] + sums["contracted"] + sums["booked"]
    total = secured + sums["expected"]
    target = sum((targets[m]["target"] for m in months), _ZERO) if has_plan else None
    return {
        "start": start, "end": period_end(granularity, start), **sums,
        "secured": secured, "total": total, "target": target,
        "possible_income": sum((targets[m]["possible"] for m in months), _ZERO),
        "gap_secured": None if target is None else target - secured,
        "gap_total": None if target is None else target - total,
    }


def get_forecast(workspace_id: int, granularity: str, today: date | None = None, offer: str | None = None) -> dict:
    """The periods to show (a little history, this one, the ones ahead), the tiles (this month,
    next month, the month after, this and next quarter, this and next year — the same whichever
    view is chosen), the money with no due day, and the plan. Run inside the workspace's scope."""
    today = today or date.today()
    starts = periods_around(granularity, today)
    tile_starts = [(key, g, shift_months(period_start(g, today), ahead * _MONTHS_LONG[g])) for key, g, ahead in TILES]
    needed = [(s, period_end(granularity, s)) for s in starts] + [(s, period_end(g, s)) for _, g, s in tile_starts]
    first, last = min(a for a, _ in needed), max(b for _, b in needed)
    plan = get_plan()
    has_plan = plan["monthly_need"] is not None
    all_months = []
    for g, s in [(granularity, s) for s in starts] + [(g, s) for _, g, s in tile_starts]:
        all_months += months_of(g, s)
    targets = month_targets(plan["monthly_need"], plan["other_income"], sorted(set(all_months)))
    money, undated, undated_count = _monthly_money(workspace_id, first, last, offer)
    periods = [_period(granularity, s, money, targets, has_plan) for s in starts]
    tiles = [{"key": key, "granularity": g, **_period(g, s, money, targets, has_plan)} for key, g, s in tile_starts]
    undated_secured = undated["contracted"] + undated["booked"]
    return {
        "granularity": granularity, "today": today, "periods": periods, "tiles": tiles, "plan": plan,
        "undated": {**undated, "secured": undated_secured, "total": undated_secured + undated["expected"],
                    "count": undated_count},
    }
