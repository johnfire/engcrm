"""Contact-detail opportunity analysis stays scoped to one admin-selected contact."""
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import gcrm.api.main as main
from gcrm.api.auth import require_admin, require_login
from gcrm.supervisor import organization_opportunity_analysis

client = TestClient(main.app)


@pytest.fixture
def admin_access():
    main.app.dependency_overrides[require_login] = lambda: "admin"
    main.app.dependency_overrides[require_admin] = lambda: "admin"
    yield
    main.app.dependency_overrides.pop(require_login, None)
    main.app.dependency_overrides.pop(require_admin, None)


def test_selected_organization_analysis_redirects_with_summary(admin_access):
    with patch("gcrm.api.routers.organizations.analyse_organization_opportunity", return_value={"summary": "saved"}) as analyse:
        response = client.post("/organizations/42/opportunity-analysis", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/organizations/42"
    analyse.assert_called_once_with(42)


def test_single_organization_runner_injects_only_selected_organization():
    # autospec so the stub enforces the real create_opportunity_agent signature —
    # a permissive **kwargs mock let a missing required dependency ship.
    captured = {}
    organization = {"id": 42, "name": "Acme", "deleted_at": None}

    class Agent:
        def invoke(self, state):
            captured["contacts"] = dependencies["fetch_organizations"](state["limit"])
            return {"summary": "saved"}

    dependencies = {}

    def create_agent(**kwargs):
        dependencies.update(kwargs)
        return Agent()

    with patch.object(organization_opportunity_analysis, "get_organization", return_value=organization), \
         patch.object(organization_opportunity_analysis, "get_llm"), \
         patch("gcrm_opportunity_agent.create_opportunity_agent",
               autospec=True, side_effect=create_agent):
        result = organization_opportunity_analysis.analyse_organization_opportunity(42)

    assert result["summary"] == "saved"
    assert captured["contacts"] == [organization]


def test_organization_template_has_accessible_analysis_progress_feedback():
    template = (Path(__file__).parents[1] / "gcrm/ui/templates/organization_detail.html").read_text()
    assert "data-opportunity-form" in template
    assert "data-opportunity-status" in template
    assert "aria-busy" in template
