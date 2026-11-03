"""Field mode: the phone's location endpoints (/api/me) and the point checks. DB mocked —
the real-schema tests are in tests/integration/test_field_locations_db.py."""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import gcrm.api.main as main
from gcrm.api.jwt_auth import create_token
from gcrm.tools.field_locations import MAX_BATCH, record_points

client = TestClient(main.app)
SHARED_ADMIN = {"Authorization": f"Bearer {create_token('admin')}"}
FIELD = "gcrm.api.routers.api_field"


def now_iso(minutes_ago=0):
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat()


class TestEndpoints:
    def call(self, method, path, json=None, headers=None, **patches):
        with patch(f"{FIELD}._personal_identity", return_value=(7, 1)), \
             patch(f"{FIELD}.record_points", return_value=patches.get("stored", 2)) as record, \
             patch(f"{FIELD}.latest_point", return_value=patches.get("latest")) as latest, \
             patch(f"{FIELD}.delete_history", return_value=5) as delete:
            response = client.request(method, path, json=json, headers=headers or SHARED_ADMIN)
        return response, record, latest, delete

    def test_stores_a_batch_for_the_signed_in_account(self):
        body = {"points": [{"latitude": 48.05, "longitude": 10.87, "accuracy_m": 9, "recorded_at": now_iso(5)},
                           {"latitude": 48.06, "longitude": 10.88, "recorded_at": now_iso()}]}
        response, record, _, _ = self.call("POST", "/api/me/locations", json=body)
        assert response.status_code == 200 and response.json() == {"stored": 2}
        user_id, points = record.call_args.args
        assert user_id == 7 and len(points) == 2 and points[1]["accuracy_m"] is None

    @pytest.mark.parametrize("bad", [
        {"latitude": 91, "longitude": 10, "recorded_at": "2026-11-03T12:00:00+00:00"},
        {"latitude": 48, "longitude": 181, "recorded_at": "2026-11-03T12:00:00+00:00"},
        {"latitude": 48, "longitude": 10, "accuracy_m": -1, "recorded_at": "2026-11-03T12:00:00+00:00"},
        {"latitude": 48, "longitude": 10},
    ])
    def test_refuses_impossible_points_before_storing_any(self, bad):
        response, record, _, _ = self.call("POST", "/api/me/locations", json={"points": [bad]})
        assert response.status_code == 422
        record.assert_not_called()

    def test_refuses_a_batch_that_is_too_big(self):
        point = {"latitude": 48, "longitude": 10, "recorded_at": now_iso()}
        response, record, _, _ = self.call("POST", "/api/me/locations", json={"points": [point] * (MAX_BATCH + 1)})
        assert response.status_code == 422
        record.assert_not_called()

    def test_reads_and_deletes_only_the_own_history(self):
        latest = {"latitude": 48.05, "longitude": 10.87, "age_seconds": 60, "stale": False}
        response, _, read, _ = self.call("GET", "/api/me/location", latest=latest)
        assert response.json() == {"location": latest}
        read.assert_called_once_with(7)
        response, _, _, delete = self.call("DELETE", "/api/me/locations")
        assert response.json() == {"deleted": 5}
        delete.assert_called_once_with(7)

    def test_needs_a_login_and_a_personal_account(self):
        assert client.get("/api/me/location").status_code in (401, 403)
        with patch(f"{FIELD}._personal_identity", return_value=(None, None)):
            response = client.get("/api/me/location", headers=SHARED_ADMIN)
        assert response.status_code == 403


class TestPointChecks:
    """record_points checks every point before writing any (DB never reached here)."""

    def test_a_point_from_the_future_is_not_a_real_fix(self):
        future = {"latitude": 48, "longitude": 10, "recorded_at": datetime.now(timezone.utc) + timedelta(hours=1)}
        with patch("gcrm.tools.field_locations.db") as db, pytest.raises(ValueError, match="point 0: .*future"):
            record_points(7, [future])
        db.assert_not_called()

    def test_a_time_without_time_zone_is_refused(self):
        with patch("gcrm.tools.field_locations.db") as db, pytest.raises(ValueError, match="time zone"):
            record_points(7, [{"latitude": 48, "longitude": 10, "recorded_at": datetime(2026, 11, 3, 12)}])
        db.assert_not_called()

    def test_an_empty_batch_writes_nothing(self):
        with patch("gcrm.tools.field_locations.db") as db:
            assert record_points(7, []) == 0
        db.assert_not_called()
