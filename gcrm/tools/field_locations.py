"""Field mode's travel history: where a user was, one point at a time.

The phone records a point every few minutes while field mode is on and sends them in
batches (points taken without signal arrive later). The newest point is "where am I
now" for the remote MCP; a point older than STALE_AFTER counts as unknown there, so a
business is never filed at a place the user left long ago. Points are kept until the
user deletes them. See docs/plans/2026-11-03-field-mode-and-remote-mcp-plan.md.
"""
from datetime import datetime, timedelta, timezone

from gcrm.db.connection import db
from gcrm.tools.db_audit import log_audit

STALE_AFTER = timedelta(minutes=10)
# A phone clock a little ahead is fine; a point from the future is not a real fix.
_CLOCK_SKEW = timedelta(minutes=5)
MAX_BATCH = 500


def _point_problem(point: dict, now: datetime) -> str | None:
    lat, lng, when = point.get("latitude"), point.get("longitude"), point.get("recorded_at")
    if not isinstance(lat, (int, float)) or not -90 <= lat <= 90:
        return "latitude must be between -90 and 90"
    if not isinstance(lng, (int, float)) or not -180 <= lng <= 180:
        return "longitude must be between -180 and 180"
    accuracy = point.get("accuracy_m")
    if accuracy is not None and (not isinstance(accuracy, (int, float)) or accuracy < 0):
        return "accuracy_m must be 0 or more"
    if not isinstance(when, datetime) or when.tzinfo is None:
        return "recorded_at must be a time with a time zone"
    if when > now + _CLOCK_SKEW:
        return "recorded_at is in the future"
    return None


def record_points(user_id: int, points: list[dict]) -> int:
    """Store a batch of points; a point already stored (same time) is skipped, so a
    retried upload is harmless. Returns how many were new. Raises ValueError, naming
    the first bad point, before anything is written."""
    if len(points) > MAX_BATCH:
        raise ValueError(f"at most {MAX_BATCH} points per upload")
    now = datetime.now(timezone.utc)
    for index, point in enumerate(points):
        problem = _point_problem(point, now)
        if problem:
            raise ValueError(f"point {index}: {problem}")
    if not points:
        return 0
    stored = 0
    with db() as conn:
        cur = conn.cursor()
        for point in points:
            cur.execute(
                "INSERT INTO field_locations (user_id, latitude, longitude, accuracy_m, recorded_at) "
                "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (user_id, recorded_at) DO NOTHING",
                (user_id, point["latitude"], point["longitude"], point.get("accuracy_m"), point["recorded_at"]),
            )
            stored += cur.rowcount
    return stored


def latest_point(user_id: int, now: datetime | None = None) -> dict | None:
    """The user's newest point with its age, and whether it is too old to trust
    (`stale`); None when they have none."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT latitude, longitude, accuracy_m, recorded_at FROM field_locations "
            "WHERE user_id = %s ORDER BY recorded_at DESC LIMIT 1",
            (user_id,),
        )
        row = cur.fetchone()
    if row is None:
        return None
    age = (now or datetime.now(timezone.utc)) - row["recorded_at"]
    return {
        "latitude": row["latitude"],
        "longitude": row["longitude"],
        "accuracy_m": row["accuracy_m"],
        "recorded_at": row["recorded_at"].isoformat(),
        "age_seconds": max(0, int(age.total_seconds())),
        "stale": age > STALE_AFTER,
    }


def delete_history(user_id: int) -> int:
    """Delete every point of this user's travel history. Returns how many went."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM field_locations WHERE user_id = %s", (user_id,))
        deleted = cur.rowcount
    log_audit(None, None, "field_locations.deleted", f"user:{user_id}", str(deleted))
    return deleted
