"""Field mode's travel history, against the real schema."""
from datetime import datetime, timedelta, timezone

import psycopg2
import pytest

from gcrm.db.connection import db
from gcrm.tools.field_locations import delete_history, latest_point, record_points

pytestmark = pytest.mark.integration

NOW = datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)


def _user(email: str) -> int:
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("INSERT INTO users (email, password_hash, role, workspace_id) "
                       "SELECT %s, 'hash', 'admin', id FROM workspaces WHERE slug = 'default' RETURNING id",
                       (email,))
        return cursor.fetchone()["id"]


def _point(minutes_ago: int, lat: float = 48.05, lng: float = 10.87) -> dict:
    return {"latitude": lat, "longitude": lng, "accuracy_m": 12.0, "recorded_at": NOW - timedelta(minutes=minutes_ago)}


def test_every_point_is_kept_and_a_retried_upload_is_stored_once(clean_database):
    user = _user("field@example.test")
    assert record_points(user, [_point(15), _point(10), _point(5)]) == 3
    # The phone lost the answer and sends the last two again, plus a new one.
    assert record_points(user, [_point(10), _point(5), _point(0, lat=48.06)]) == 1
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT count(*) AS n FROM field_locations WHERE user_id = %s", (user,))
        assert cursor.fetchone()["n"] == 4


def test_where_am_i_is_the_newest_point_and_goes_stale(clean_database):
    user = _user("field@example.test")
    assert latest_point(user, now=NOW) is None
    # Sent out of order (an offline batch arriving late): the newest fix still wins.
    record_points(user, [_point(2, lat=48.10), _point(30, lat=48.00)])
    here = latest_point(user, now=NOW)
    assert here["latitude"] == 48.10 and here["age_seconds"] == 120 and here["stale"] is False
    assert latest_point(user, now=NOW + timedelta(minutes=9))["stale"] is True  # 11 minutes old


def test_each_user_sees_and_deletes_only_their_own_history(clean_database):
    chris, other = _user("chris@example.test"), _user("other@example.test")
    record_points(chris, [_point(5, lat=48.1), _point(1, lat=48.2)])
    record_points(other, [_point(1, lat=52.5)])
    assert latest_point(other, now=NOW)["latitude"] == 52.5
    assert delete_history(chris) == 2
    assert latest_point(chris, now=NOW) is None
    assert latest_point(other, now=NOW)["latitude"] == 52.5


def test_the_database_refuses_impossible_points(clean_database):
    user = _user("field@example.test")
    with db() as connection, pytest.raises(psycopg2.errors.CheckViolation):
        connection.cursor().execute(
            "INSERT INTO field_locations (user_id, latitude, longitude, recorded_at) VALUES (%s, 91, 10, NOW())",
            (user,))
