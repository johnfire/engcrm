"""Statistics over time: the daily pipeline log, and series per week, month or year.

Activities, hours, sales and new contacts are computed from the records, so their
series reach back to the start. The pipeline's size per stage can't be rebuilt
for a past day, so `record_pipeline_snapshot` logs it daily; its series starts
the day the log did.
"""
import logging
import threading
import time
from datetime import date, timedelta
from decimal import Decimal

from gcrm.activity_types import NOT_ACTIVITIES
from gcrm.db.connection import db
from gcrm.tools.statistics import activities_sql, get_minute_defaults

logger = logging.getLogger(__name__)

BUCKETS = {"week": 12, "month": 12, "year": 5}  # bucket -> how many of them a chart shows
SNAPSHOT_LOCK = 735_061  # advisory lock: one snapshot write at a time across workers
SNAPSHOT_EVERY_SECONDS = 3600


def record_pipeline_snapshot(day: date | None = None) -> int:
    """Write today's stage counts for every workspace, replacing any earlier
    snapshot of the same day. Returns the rows written."""
    day = day or date.today()
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT pg_advisory_xact_lock(%s)", (SNAPSHOT_LOCK,))
        cur.execute("DELETE FROM pipeline_snapshots WHERE day = %s", (day,))
        cur.execute(
            """
            INSERT INTO pipeline_snapshots (workspace_id, day, entity_type, stage, n)
            SELECT workspace_id, %s, 'organization', pipeline_stage, COUNT(*) FROM contacts
             WHERE deleted_at IS NULL AND workspace_id IS NOT NULL AND pipeline_stage IS NOT NULL
             GROUP BY workspace_id, pipeline_stage
            UNION ALL
            SELECT workspace_id, %s, 'person', pipeline_stage, COUNT(*) FROM people
             WHERE deleted_at IS NULL AND workspace_id IS NOT NULL AND pipeline_stage IS NOT NULL
             GROUP BY workspace_id, pipeline_stage
            """,
            (day, day),
        )
        return cur.rowcount


def _snapshot_loop() -> None:
    while True:
        try:
            record_pipeline_snapshot()
        except Exception:
            logger.exception("pipeline snapshot failed; trying again in an hour")
        time.sleep(SNAPSHOT_EVERY_SECONDS)


def start_snapshot_loop() -> threading.Thread:
    """Keep the daily pipeline log in the background of the running app."""
    thread = threading.Thread(target=_snapshot_loop, daemon=True, name="pipeline-snapshots")
    thread.start()
    return thread


def bucket_start(bucket: str, day: date) -> date:
    """The first day of the week (Monday), month or year `day` falls in."""
    if bucket == "week":
        return day - timedelta(days=day.weekday())
    if bucket == "month":
        return day.replace(day=1)
    if bucket == "year":
        return date(day.year, 1, 1)
    raise ValueError(f"unknown bucket {bucket!r}")


def bucket_starts(bucket: str, today: date) -> list[date]:
    """The first day of each of the last BUCKETS[bucket] weeks/months/years, oldest first."""
    count = BUCKETS[bucket]
    if bucket == "week":
        this = today - timedelta(days=today.weekday())
        return [this - timedelta(weeks=n) for n in range(count - 1, -1, -1)]
    if bucket == "month":
        starts, year, month = [], today.year, today.month
        for _ in range(count):
            starts.append(date(year, month, 1))
            year, month = (year, month - 1) if month > 1 else (year - 1, 12)
        return starts[::-1]
    if bucket == "year":
        return [date(today.year - n, 1, 1) for n in range(count - 1, -1, -1)]
    raise ValueError(f"unknown bucket {bucket!r}")


def get_series(workspace_id: int, bucket: str, today: date | None = None) -> dict:
    """Per bucket: activities, hours, € won, new organizations and people; and the
    pipeline per stage as logged on the last logged day of each bucket."""
    today = today or date.today()
    starts = bucket_starts(bucket, today)
    first = starts[0]
    trunc = {"week": "week", "month": "month", "year": "year"}[bucket]
    acts_sql, acts_params = activities_sql(get_minute_defaults(workspace_id))
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            f"WITH {acts_sql} SELECT date_trunc('{trunc}', day)::date AS b, "
            "COUNT(*) FILTER (WHERE kind <> 'note') AS n, COALESCE(SUM(minutes), 0) AS minutes "
            "FROM acts WHERE day BETWEEN %s AND %s GROUP BY 1",
            acts_params + [workspace_id, workspace_id, *NOT_ACTIVITIES, first, today],
        )
        effort = {row["b"]: row for row in cur.fetchall()}
        cur.execute(
            f"SELECT date_trunc('{trunc}', won_on)::date AS b, SUM(amount_eur) AS won FROM sales "
            "WHERE workspace_id = %s AND deleted_at IS NULL AND won_on BETWEEN %s AND %s GROUP BY 1",
            (workspace_id, first, today),
        )
        won = {row["b"]: row["won"] for row in cur.fetchall()}
        cur.execute(
            f"SELECT date_trunc('{trunc}', created_at)::date AS b, 'organization' AS kind, COUNT(*) AS n "
            "FROM contacts WHERE workspace_id = %s AND deleted_at IS NULL AND created_at::date BETWEEN %s AND %s "
            "GROUP BY 1 UNION ALL "
            f"SELECT date_trunc('{trunc}', created_at)::date, 'person', COUNT(*) FROM people "
            "WHERE workspace_id = %s AND deleted_at IS NULL AND created_at::date BETWEEN %s AND %s GROUP BY 1",
            (workspace_id, first, today, workspace_id, first, today),
        )
        new = {}
        for row in cur.fetchall():
            new.setdefault(row["b"], {})[row["kind"]] = row["n"]
        cur.execute(
            "SELECT day, entity_type, stage, n FROM pipeline_snapshots "
            "WHERE workspace_id = %s AND day BETWEEN %s AND %s ORDER BY day",
            (workspace_id, first, today),
        )
        rows = cur.fetchall()
        # Each bucket shows its last logged day: find that day, then keep only its rows.
        last_day: dict = {}
        for row in rows:
            b = bucket_start(bucket, row["day"])
            last_day[b] = max(last_day.get(b, row["day"]), row["day"])
        pipeline: dict = {}
        for row in rows:
            b = bucket_start(bucket, row["day"])
            if row["day"] == last_day[b]:
                pipeline.setdefault(row["entity_type"], {}).setdefault(row["stage"], {})[b] = row["n"]
        cur.execute("SELECT MIN(day) AS first FROM pipeline_snapshots WHERE workspace_id = %s", (workspace_id,))
        logged_since = cur.fetchone()["first"]

    periods = []
    for start in starts:
        e = effort.get(start)
        periods.append({
            "start": start,
            "activities": e["n"] if e else 0,
            "hours": round(int(e["minutes"]) / 60, 1) if e else 0.0,
            "won_eur": Decimal(won.get(start) or 0),
            "new_organizations": new.get(start, {}).get("organization", 0),
            "new_people": new.get(start, {}).get("person", 0),
        })
    return {"bucket": bucket, "periods": periods, "pipeline": pipeline, "logged_since": logged_since}
