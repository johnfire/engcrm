"""Hours of work booked per week, for the Forecast page.

Entered hours come from the sales (not cancelled): a sale's hours are spread evenly over the days of its work
window, or over the calendar month its payment is due in when it has none (a received sale: the month it was
received; no due day at all: the month it was won). The expected hours are an assumption: the plan's new bookings
each ask for a number of hours a week, from the month they are paying, as counted for the Projected column.
Run inside the workspace's scope.
"""
from datetime import date, timedelta
from decimal import Decimal

from gcrm.db.connection import db
from gcrm.forecast_math import hours_window, live_bookings, month_index, spread_hours, week_start
from gcrm.tools.income_plan import get_plan
from gcrm.tools.revenue import live_sales_sql

_ZERO = Decimal("0")
DEFAULT_WEEKS = 13


def _window(row) -> tuple[date, date]:
    due = row["collected_on"] if row["status"] == "collected" and row["collected_on"] else row["expected_on"]
    return hours_window(row["work_from"], row["work_to"], due or row["won_on"])


def get_weekly_hours(workspace_id: int, today: date | None = None, weeks: int = DEFAULT_WEEKS, offer: str | None = None) -> dict:
    """{"weeks": [{start, end, entered, expected, total}], "capacity", "has_expected"} for `weeks` weeks from the
    Monday of this week. Hours are Decimals; a week with none has zero."""
    today = today or date.today()
    plan = get_plan()
    first = week_start(today)
    starts = [first + timedelta(weeks=i) for i in range(weeks)]
    entered = {start: _ZERO for start in starts}
    scope, params = live_sales_sql(workspace_id, offer)
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT s.status, s.hours, s.work_from, s.work_to, s.expected_on, s.collected_on, s.won_on "
                    f"{scope} AND s.status <> 'cancelled' AND s.hours IS NOT NULL", params)
        for row in cur.fetchall():
            for monday, hours in spread_hours(Decimal(row["hours"]), *_window(row)).items():
                if monday in entered:
                    entered[monday] += hours
    per_booking = plan["expected_new_hours"]
    has_expected = bool(plan["expected_new_monthly"]) and bool(per_booking)
    this_month = today.replace(day=1)
    result = []
    for start in starts:
        thursday = start + timedelta(days=3)              # the week belongs to the month most of it is in
        expected = _ZERO
        if has_expected:
            index = month_index(this_month, thursday.replace(day=1))
            if index >= 0:
                expected = Decimal(per_booking) * live_bookings(index, plan["expected_new_months"], plan["expected_new_delay"],
                                                                plan["expected_new_campaign"])
        result.append({"start": start, "end": start + timedelta(days=6), "entered": entered[start], "expected": expected,
                       "total": entered[start] + expected})
    return {"weeks": result, "capacity": plan["weekly_capacity"], "has_expected": has_expected}
