"""Deleting a wrong entry from an organization's interaction history on the web page:
POST /organizations/{id}/interactions/{iid}/delete soft-deletes it and comes back."""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import gcrm.api.main as main
from gcrm.api.auth import require_admin, require_login

client = TestClient(main.app)


@pytest.fixture
def admin_web():
    main.app.dependency_overrides[require_login] = lambda: "admin"
    main.app.dependency_overrides[require_admin] = lambda: "admin"
    yield
    main.app.dependency_overrides.pop(require_login, None)
    main.app.dependency_overrides.pop(require_admin, None)


def test_delete_interaction_soft_deletes_and_returns_to_the_organization(admin_web):
    with patch("gcrm.api.routers.organizations.delete_meeting_note", return_value=True) as delete:
        response = client.post("/organizations/1183/interactions/55/delete", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/organizations/1183?saved=1"
    delete.assert_called_once_with(1183, 55)


def test_delete_interaction_that_is_missing_is_404(admin_web):
    with patch("gcrm.api.routers.organizations.delete_meeting_note", return_value=False):
        response = client.post("/organizations/1183/interactions/999/delete", follow_redirects=False)

    assert response.status_code == 404


def test_delete_interaction_needs_login():
    with patch("gcrm.api.routers.organizations.delete_meeting_note") as delete:
        response = client.post("/organizations/1183/interactions/55/delete", follow_redirects=False)

    assert response.status_code in (303, 307, 401, 403)
    delete.assert_not_called()
