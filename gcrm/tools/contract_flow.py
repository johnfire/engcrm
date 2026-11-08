"""Contract flow: how much business was entered when, the running total, and money in against the target.

Everything the owner has entered at "expected" or above counts (expected, booked, contracted,
collected); cancelled money is left out. A sale sits in the bucket (week, month or year) of the
date it was won (`won_on`), and a contract paid in monthly payments is one deal, entered once, in
the bucket of the day it was won. Money in is the sales collected, on the day the money came in,
plus the confirmed other income, spread over the days of the months it covers; the target is the
plan's monthly need spread the same way, up to today. Run inside the workspace's scope.
"""
from datetime import date
from decimal import Decimal

from gcrm.db.connection import db
from gcrm.flow_math import bucket_end, bucket_start, daily_pace, flow_buckets
from gcrm.tools.income_plan import get_plan
from gcrm.tools.revenue import live_sales_sql

ENTERED_STATUSES = ("expected", "booked", "contracted", "collected")
_STATUS_LIST = ", ".join(f"'{status}'" for status in ENTERED_STATUSES)     # constants, never input
_ZERO = Decimal("0")
_CENT = Decimal("0.01")


def _first_sale_month(cur, workspace_id: int, offer: str | None) -> date | None:
    scope, params = live_sales_sql(workspace_id, offer)
    cur.execute(f"SELECT MIN(s.won_on) AS first {scope} AND s.status IN ({_STATUS_LIST})", params)
    first = cur.fetchone()["first"]
    return first.replace(day=1) if first else None


def get_contract_flow(workspace_id: int, range_key: str, today: date | None = None, offer: str | None = None) -> dict:
    """{"granularity", "has_target", "buckets": [...]} for the range ("3m", "year" or "all"). A bucket:
    start, end, entered {status: €}, entered_total, deals, cumulative (everything entered up to the
    end of the bucket, including before the window), sales_in, other_in, money_in, target, and the
    running cum_money_in / cum_target from the start of the window. Raises ValueError for a range
    it does not know."""
    today = today or date.today()
    plan = get_plan()
    with db() as conn:
        cur = conn.cursor()
        first_month = None
        if range_key == "all":
            first_month = plan["start_month"] or _first_sale_month(cur, workspace_id, offer)
        granularity, starts = flow_buckets(range_key, today, first_month)
        window_start = starts[0]
        scope, params = live_sales_sql(workspace_id, offer)
        bucket = f"date_trunc('{granularity}', s.won_on)::date"                  # granularity is one of three constants
        entered_in_window = f"{scope} AND s.status IN ({_STATUS_LIST}) AND s.won_on BETWEEN %s AND %s"
        cur.execute(f"SELECT {bucket} AS b, s.status, SUM(s.amount_eur) AS eur {entered_in_window} GROUP BY 1, 2",
                    [*params, window_start, today])
        entered_rows = cur.fetchall()
        cur.execute(f"SELECT {bucket} AS b, COUNT(DISTINCT COALESCE(s.series_id::text, s.id::text)) AS n "
                    f"{entered_in_window} GROUP BY 1", [*params, window_start, today])
        deals = {row["b"]: row["n"] for row in cur.fetchall()}
        cur.execute(f"SELECT COALESCE(SUM(s.amount_eur), 0) AS eur {scope} AND s.status IN ({_STATUS_LIST}) "
                    "AND s.won_on < %s", [*params, window_start])
        base = Decimal(cur.fetchone()["eur"])
        cur.execute(f"SELECT s.collected_on AS d, SUM(s.amount_eur) AS eur {scope} AND s.status = 'collected' "
                    "AND s.collected_on BETWEEN %s AND %s GROUP BY 1", [*params, window_start, today])
        collected_by_day = {row["d"]: Decimal(row["eur"]) for row in cur.fetchall()}
    entered: dict[date, dict] = {}
    for row in entered_rows:
        entered.setdefault(row["b"], {status: _ZERO for status in ENTERED_STATUSES})[row["status"]] = Decimal(row["eur"])
    pace = daily_pace(plan["monthly_need"], plan["other_income"], plan["start_month"], window_start, today)
    per_bucket: dict[date, dict] = {start: {"sales": _ZERO, "other": _ZERO, "target": _ZERO} for start in starts}
    for day, share in pace.items():
        per_bucket[bucket_start(granularity, day)]["other"] += share["covered"]
        per_bucket[bucket_start(granularity, day)]["target"] += share["target"]
    for day, euros in collected_by_day.items():
        per_bucket[bucket_start(granularity, day)]["sales"] += euros
    buckets, running, money_in, target = [], base, _ZERO, _ZERO
    for start in starts:
        by_status = entered.get(start, {status: _ZERO for status in ENTERED_STATUSES})
        total = sum(by_status.values(), _ZERO)
        running += total
        flows = per_bucket[start]
        money_in += flows["sales"] + flows["other"]
        target += flows["target"]
        buckets.append({
            "start": start, "end": min(bucket_end(granularity, start), today),
            "entered": by_status, "entered_total": total, "deals": deals.get(start, 0), "cumulative": running,
            "sales_in": flows["sales"].quantize(_CENT), "other_in": flows["other"].quantize(_CENT),
            "money_in": (flows["sales"] + flows["other"]).quantize(_CENT), "target": flows["target"].quantize(_CENT),
            "cum_money_in": money_in.quantize(_CENT), "cum_target": target.quantize(_CENT),
        })
    return {"range": range_key, "granularity": granularity, "today": today,
            "has_target": plan["monthly_need"] is not None, "buckets": buckets}
