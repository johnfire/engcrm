"""What is coming in, and when: money by month, quarter or year against a target.

Each sale row (a one-off, or one payment of a contract) sits in the month of its due day
(`expected_on`), or of the day it was received (`collected_on`) once collected. Cancelled
money is left out. Money with no due day is reported apart as "undated" instead of vanishing.

  collected   received      contracted  a written contract exists   booked    agreed
  expected    a hope        subtotal = collected + contracted + booked + expected (the sales)
  other income = confirmed income from the plan that covers the period (counts toward the target)
  total (the grand total) = subtotal + other income

The target is the income plan's monthly need (gcrm/tools/income_plan.py), the same every month,
summed for a quarter or year; "still missing" is target minus total. Nothing here weights money by likelihood: it is what it is.
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
from gcrm.tools.income_plan import get_plan
from gcrm.tools.revenue import live_sales_sql

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
    scope, params = live_sales_sql(workspace_id, offer)
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT date_trunc('month', due)::date AS month, status, SUM(amount_eur) AS eur, COUNT(*) AS n FROM ("
            "  SELECT s.status, s.amount_eur, CASE WHEN s.status = 'collected' THEN s.collected_on ELSE s.expected_on END AS due "
            f"  {scope} AND s.status <> 'cancelled'"
            ") x WHERE due IS NULL OR due BETWEEN %s AND %s GROUP BY 1, 2",
            [*params, first, last],
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


def _period(granularity: str, start: date, money: dict, targets: dict) -> dict:
    months = months_of(granularity, start)
    sums = _blank()
    for month in months:
        for status, euros in money.get(month, {}).items():
            sums[status] += euros
    subtotal = sums["collected"] + sums["contracted"] + sums["booked"] + sums["expected"]
    covered = sum((targets[m]["covered"] for m in months), _ZERO)
    total = subtotal + covered
    counted = [targets[m]["target"] for m in months if targets[m]["target"] is not None]
    target = sum(counted, _ZERO) if counted else None            # months before the business started count for nothing
    return {
        "start": start, "end": period_end(granularity, start), **sums,
        "subtotal": subtotal, "total": total, "target": target,
        "possible_income": sum((targets[m]["possible"] for m in months), _ZERO),
        "covered": covered,
        "gap_total": None if target is None else target - total,
    }


def get_forecast(workspace_id: int, granularity: str, today: date | None = None, offer: str | None = None) -> dict:
    """The periods to show (this year from its first month in business, through the end of next year), the tiles (this month,
    next month, the month after, this and next quarter, this and next year — the same whichever
    view is chosen), the money with no due day, and the plan. Run inside the workspace's scope."""
    today = today or date.today()
    plan = get_plan()
    first_month = plan["start_month"]
    # A period that ended before the business started has nothing to show: leave it out.
    starts = [s for s in periods_around(granularity, today, first_month)
              if first_month is None or period_end(granularity, s) >= first_month]
    tile_starts = [(key, g, shift_months(period_start(g, today), ahead * _MONTHS_LONG[g])) for key, g, ahead in TILES]
    needed = [(s, period_end(granularity, s)) for s in starts] + [(s, period_end(g, s)) for _, g, s in tile_starts]
    first, last = min(a for a, _ in needed), max(b for _, b in needed)
    all_months = []
    for g, s in [(granularity, s) for s in starts] + [(g, s) for _, g, s in tile_starts]:
        all_months += months_of(g, s)
    targets = month_targets(plan["monthly_need"], plan["other_income"], sorted(set(all_months)), plan["start_month"])
    money, undated, undated_count = _monthly_money(workspace_id, first, last, offer)
    periods = [_period(granularity, s, money, targets) for s in starts]
    tiles = [{"key": key, "granularity": g, **_period(g, s, money, targets)} for key, g, s in tile_starts]
    return {
        "granularity": granularity, "today": today, "periods": periods, "tiles": tiles, "plan": plan,
        "undated": {**undated, "total": undated["contracted"] + undated["booked"] + undated["expected"],
                    "count": undated_count},
    }
