"""Contract flow: how much business was entered when, the running total, and money in against the target.

Everything the owner has entered at "expected" or above counts (expected, booked, contracted,
collected); cancelled money is left out. A sale sits in the bucket (week, month or year) of the
day it was entered: the date it was won (`won_on`), or the day it was recorded if "date won" lies in
the future (a payment day typed into it still counts from now). A contract paid in monthly payments is
one deal, entered once, in the bucket of that day. Money in is the sales collected, on the day the money came in,
plus the confirmed other income, spread over the days of the months it covers; the target is the
plan's monthly need spread the same way, up to today.

The outlook adds twelve months ahead. Its projection is not a guess about deals not yet won: it is
what is already scheduled, month by month — what has been collected, plus every unreceived sale on
its due day (a late payment counts in the current month), plus the confirmed other income for the
months it covers. A sale with no due day cannot be placed and is reported apart. Run inside the
workspace's scope.
"""
from datetime import date
from decimal import Decimal

from gcrm.db.connection import db
from gcrm.flow_math import bucket_end, bucket_start, daily_pace, flow_buckets
from gcrm.sale_series import shift_months
from gcrm.tools.income_plan import get_plan
from gcrm.tools.revenue import live_sales_sql

ENTERED_STATUSES = ("expected", "booked", "contracted", "collected")
_STATUS_LIST = ", ".join(f"'{status}'" for status in ENTERED_STATUSES)     # constants, never input
_ZERO = Decimal("0")
_CENT = Decimal("0.01")
ENTERED_ON = "LEAST(s.won_on, s.created_at::date)"     # a future "date won" counts from the day it was recorded


def _first_sale_month(cur, workspace_id: int, offer: str | None) -> date | None:
    scope, params = live_sales_sql(workspace_id, offer)
    cur.execute(f"SELECT MIN({ENTERED_ON}) AS first {scope} AND s.status IN ({_STATUS_LIST})", params)
    first = cur.fetchone()["first"]
    return first.replace(day=1) if first else None


def _scheduled_sales(cur, scope: str, params: list, today: date) -> tuple[dict[date, Decimal], dict]:
    """({month: € still to arrive}, {"count", "total", "items"} of the unreceived sales with no due day)
    for the outlook. A sale received on a day still to come counts on that day. A payment whose due day
    has passed counts in the current month: it is still expected, so it is not left in the past. The
    sales with no due day cannot be placed: each is listed (who, how much, which status) so it can be fixed."""
    cur.execute(
        "SELECT date_trunc('month', due)::date AS month, SUM(amount) AS eur FROM ("
        "  SELECT s.amount_eur AS amount, CASE WHEN s.status = 'collected' THEN s.collected_on ELSE s.expected_on END AS due "
        f"  {scope} AND s.status IN ({_STATUS_LIST}) AND (s.status <> 'collected' OR s.collected_on > %s)"
        ") x WHERE due IS NOT NULL GROUP BY 1",
        [*params, today],
    )
    this_month = today.replace(day=1)
    scheduled: dict[date, Decimal] = {}
    for row in cur.fetchall():
        month = max(row["month"], this_month)
        scheduled[month] = scheduled.get(month, _ZERO) + Decimal(row["eur"])
    cur.execute(
        "SELECT s.id AS sale_id, s.deal_id, s.status, s.amount_eur, s.description, c.id AS organization_id, "
        f"c.name AS organization_name, p.id AS person_id, p.name AS person_name {scope} "
        "AND s.status IN ('expected', 'booked', 'contracted') AND s.expected_on IS NULL ORDER BY s.won_on, s.id",
        params,
    )
    items = [{**dict(row), "amount_eur": Decimal(row["amount_eur"])} for row in cur.fetchall()]
    return scheduled, {"count": len(items), "total": sum((item["amount_eur"] for item in items), _ZERO), "items": items}


def get_contract_flow(workspace_id: int, range_key: str, today: date | None = None, offer: str | None = None) -> dict:
    """{"range", "granularity", "has_target", "today", "undated", "buckets": [...]} for the range ("3m",
    "year", "all" or "outlook"). A bucket: start, end, future (it begins after today), entered {status: €},
    entered_total, deals, cumulative (everything entered up to the end of the bucket, including before the
    window), sales_in, other_in, money_in, target, and the running cum_money_in / cum_target from the start
    of the window (None for a future bucket's money in). In the outlook the target is the whole month's, and
    each bucket also has projection (running, month end; None before last month), proj_sales (still to
    arrive that month) and proj_other (other income covering it); `undated` counts the sales with no due
    day. Raises ValueError for a range it does not know."""
    today = today or date.today()
    plan = get_plan()
    outlook = range_key == "outlook"
    with db() as conn:
        cur = conn.cursor()
        first_month = None
        if range_key in ("all", "outlook"):
            first_month = plan["start_month"] or _first_sale_month(cur, workspace_id, offer)
        granularity, starts = flow_buckets(range_key, today, first_month)
        window_start = starts[0]
        scope, params = live_sales_sql(workspace_id, offer)
        bucket = f"date_trunc('{granularity}', {ENTERED_ON})::date"             # granularity is one of three constants
        entered_in_window = f"{scope} AND s.status IN ({_STATUS_LIST}) AND {ENTERED_ON} BETWEEN %s AND %s"
        cur.execute(f"SELECT {bucket} AS b, s.status, SUM(s.amount_eur) AS eur {entered_in_window} GROUP BY 1, 2",
                    [*params, window_start, today])
        entered_rows = cur.fetchall()
        cur.execute(f"SELECT {bucket} AS b, COUNT(DISTINCT COALESCE(s.series_id::text, s.id::text)) AS n "
                    f"{entered_in_window} GROUP BY 1", [*params, window_start, today])
        deals = {row["b"]: row["n"] for row in cur.fetchall()}
        cur.execute(f"SELECT COALESCE(SUM(s.amount_eur), 0) AS eur {scope} AND s.status IN ({_STATUS_LIST}) "
                    f"AND {ENTERED_ON} < %s", [*params, window_start])
        base = Decimal(cur.fetchone()["eur"])
        cur.execute(f"SELECT s.collected_on AS d, SUM(s.amount_eur) AS eur {scope} AND s.status = 'collected' "
                    "AND s.collected_on BETWEEN %s AND %s GROUP BY 1", [*params, window_start, today])
        collected_by_day = {row["d"]: Decimal(row["eur"]) for row in cur.fetchall()}
        scheduled, undated = _scheduled_sales(cur, scope, params, today) if outlook else ({}, None)
    entered: dict[date, dict] = {}
    for row in entered_rows:
        entered.setdefault(row["b"], {status: _ZERO for status in ENTERED_STATUSES})[row["status"]] = Decimal(row["eur"])
    last_day = bucket_end(granularity, starts[-1]) if outlook else today
    pace = daily_pace(plan["monthly_need"], plan["other_income"], plan["start_month"], window_start, last_day)
    per_bucket: dict[date, dict] = {start: {"sales": _ZERO, "other": _ZERO, "target": _ZERO, "other_full": _ZERO,
                                            "target_full": _ZERO} for start in starts}
    for day, share in pace.items():
        slot = per_bucket[bucket_start(granularity, day)]
        slot["other_full"] += share["covered"]
        slot["target_full"] += share["target"]
        if day <= today:
            slot["other"] += share["covered"]
            slot["target"] += share["target"]
    for day, euros in collected_by_day.items():
        per_bucket[bucket_start(granularity, day)]["sales"] += euros
    collected_total = sum(collected_by_day.values(), _ZERO)
    this_month, last_month = today.replace(day=1), shift_months(today.replace(day=1), -1)
    buckets, running, money_in, target = [], base, _ZERO, _ZERO
    other_through, scheduled_through = _ZERO, _ZERO
    expected_new = (plan["expected_new_monthly"] or None) if outlook else None             # 0 draws nothing
    paying_months = plan["expected_new_months"]                                            # None: for ever
    months_of_new, new_total = 0, _ZERO
    for start in starts:
        by_status = entered.get(start, {status: _ZERO for status in ENTERED_STATUSES})
        total = sum(by_status.values(), _ZERO)
        running += total
        flows = per_bucket[start]
        future = start > today
        money_in += flows["sales"] + flows["other"]
        target += flows["target_full"] if outlook else flows["target"]
        bucket = {
            "start": start, "end": bucket_end(granularity, start), "future": future,
            "entered": by_status, "entered_total": total, "deals": deals.get(start, 0), "cumulative": running,
            "sales_in": None if future else flows["sales"].quantize(_CENT),
            "other_in": None if future else flows["other"].quantize(_CENT),
            "money_in": None if future else (flows["sales"] + flows["other"]).quantize(_CENT),
            "target": (flows["target_full"] if outlook else flows["target"]).quantize(_CENT),
            "cum_money_in": None if future else money_in.quantize(_CENT), "cum_target": target.quantize(_CENT),
            "projection": None, "proj_sales": None, "proj_other": None, "with_new": None,
        }
        if outlook:
            other_through += flows["other_full"]
            scheduled_through += scheduled.get(start, _ZERO)
            bucket["proj_sales"] = scheduled.get(start, _ZERO).quantize(_CENT)
            bucket["proj_other"] = flows["other_full"].quantize(_CENT)
            if start >= this_month:
                months_of_new += 1
                if expected_new:        # bookings still paying this month: this month's and the earlier ones within the run
                    live = months_of_new if paying_months is None else min(months_of_new, paying_months)
                    new_total += expected_new * live
                bucket["projection"] = (collected_total + other_through + scheduled_through).quantize(_CENT)
                if expected_new:
                    bucket["with_new"] = (bucket["projection"] + new_total).quantize(_CENT)
            elif start == last_month:
                bucket["projection"] = bucket["cum_money_in"]              # joins the projection to what really came in
                bucket["with_new"] = bucket["projection"] if expected_new else None
        buckets.append(bucket)
    return {"range": range_key, "granularity": granularity, "today": today, "undated": undated,
            "expected_new": expected_new, "expected_new_months": paying_months, "has_target": plan["monthly_need"] is not None, "buckets": buckets}
