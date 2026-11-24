"""Follow-up web routes expose the review and task actions to signed-in users."""
from unittest.mock import patch

from fastapi.testclient import TestClient

from gcrm.api.auth import require_admin, require_login
from gcrm.api.main import app

client = TestClient(app)


def test_follow_up_page_shows_filters_and_review_link():
    app.dependency_overrides[require_login] = lambda: "admin"
    try:
        with patch("gcrm.api.routers.follow_ups.find_follow_ups", return_value=[]), \
             patch("gcrm.api.routers.follow_ups.list_offers", return_value=[]), \
             patch("gcrm.api.routers.follow_ups.list_follow_up_people", return_value=[]), \
             patch("gcrm.api.routers.follow_ups.list_follow_up_targets", return_value=[]):
            response = client.get("/follow-ups/")
        assert response.status_code == 200
        assert "Review older follow-ups" in response.text
        assert 'name="direction"' in response.text
        assert "Undated follow-ups remain visible" in response.text
    finally:
        app.dependency_overrides.pop(require_login, None)


def test_follow_up_completion_uses_identity_and_version():
    app.dependency_overrides[require_login] = lambda: "admin"
    app.dependency_overrides[require_admin] = lambda: "admin"
    try:
        with patch("gcrm.api.routers.follow_ups.change_follow_up_status") as change:
            response = client.post("/follow-ups/17/status", data={"status": "completed",
                                   "version": "2026-11-24T09:00:00+00:00"}, follow_redirects=False)
        assert response.status_code == 303
        assert change.call_args.args[:2] == (17, "completed")
    finally:
        app.dependency_overrides.pop(require_login, None)
        app.dependency_overrides.pop(require_admin, None)
