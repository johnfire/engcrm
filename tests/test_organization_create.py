"""Manual website entry, errors, authorization, and request audit identity."""
from unittest.mock import patch

import pytest
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient

from gcrm.api.auth import require_admin
from gcrm.api.jwt_auth import create_token
from gcrm.api.main import app
from gcrm.audit_context import current_audit_context
from gcrm.workspace_context import get_workspace_id

WEB = "gcrm.api.routers.organization_create"
API = "gcrm.api.routers.api_record_edit"


@pytest.fixture
def admin_browser():
    def signed_in(request: Request):
        request.session.update(role="admin", email="owner@example.test")
        return "admin"
    app.dependency_overrides[require_admin] = signed_in
    yield TestClient(app)
    app.dependency_overrides.pop(require_admin, None)


def test_new_form_has_all_fields_and_stages_and_localized_labels(admin_browser):
    response = admin_browser.get("/organizations/new")
    assert response.status_code == 200
    assert "Add business" in response.text and 'name="name"' in response.text
    assert 'value="candidate" selected' in response.text
    assert 'value="customer"' in response.text and 'value="not_in_pipeline"' in response.text
    assert 'name="notes"' in response.text and 'name="email"' in response.text
    assert 'value="DE"' in response.text
    assert "Unternehmen hinzufügen" in admin_browser.get("/organizations/new?lang=de").text


def test_web_save_passes_stage_and_sets_actor_and_correlation(admin_browser):
    def saved(body):
        assert body.name == "Acme" and body.pipeline_stage == "customer"
        assert current_audit_context().actor == "owner@example.test"
        assert current_audit_context().correlation_id == "manual-web-test"
        return {"id": 77}
    with patch(f"{WEB}.save_manual_organization", side_effect=saved):
        response = admin_browser.post("/organizations/new", data={"name": "Acme", "pipeline_stage": "customer"},
                                      headers={"X-Request-ID": "manual-web-test"}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/organizations/77"


@pytest.mark.parametrize("failure,status,link", [
    (HTTPException(400, "Name is required"), 400, False),
    (HTTPException(409, {"message": "Already exists", "existing_id": 7}), 409, True),
    (HTTPException(409, {"message": "Ignored chain", "existing_id": None}), 409, False),
    (RuntimeError("offline"), 503, False),
])
def test_failed_save_preserves_values_and_selected_stage(admin_browser, failure, status, link):
    with patch(f"{WEB}.save_manual_organization", side_effect=failure):
        response = admin_browser.post("/organizations/new", data={
            "name": "Acme <test>", "pipeline_stage": "opportunity", "notes": "Keep my notes",
        })
    assert response.status_code == status
    assert 'value="opportunity" selected' in response.text
    assert "Acme &lt;test&gt;" in response.text and "Keep my notes" in response.text
    assert ('href="/organizations/7"' in response.text) == link


def test_unauthenticated_web_entry_cannot_render_or_save():
    browser = TestClient(app)
    for method in (browser.get, browser.post):
        with patch(f"{WEB}.save_manual_organization") as save:
            response = method("/organizations/new", follow_redirects=False)
        assert response.status_code == 307 and response.headers["location"] == "/login"
        save.assert_not_called()


def test_mobile_creation_sets_workspace_and_audit_identity():
    def saved(body):
        assert get_workspace_id() == 42
        assert current_audit_context().actor == "shared-admin"
        assert current_audit_context().correlation_id == "manual-api-test"
        return {"id": 77}
    with patch(f"{API}._personal_identity", return_value=(None, 42)), \
         patch(f"{API}.save_manual_organization", side_effect=saved):
        response = TestClient(app).post("/api/contacts", json={"name": "Acme"}, headers={
            "Authorization": f"Bearer {create_token('admin')}", "X-Request-ID": "manual-api-test",
        })
    assert response.status_code == 200 and response.json() == {"id": 77}
