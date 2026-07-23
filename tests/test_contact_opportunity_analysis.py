"""Contact-detail opportunity analysis stays scoped to one admin-selected contact."""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import gcrm.api.main as main
from gcrm.api.auth import require_admin, require_login
from gcrm.supervisor import contact_opportunity_analysis

client = TestClient(main.app)


@pytest.fixture
def admin_access():
    main.app.dependency_overrides[require_login] = lambda: "admin"
    main.app.dependency_overrides[require_admin] = lambda: "admin"
    yield
    main.app.dependency_overrides.pop(require_login, None)
    main.app.dependency_overrides.pop(require_admin, None)


def test_selected_contact_analysis_redirects_with_summary(admin_access):
    with patch("gcrm.api.routers.contacts.analyse_contact_opportunity", return_value={"summary": "saved"}) as analyse:
        response = client.post("/contacts/42/opportunity-analysis", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/contacts/42"
    analyse.assert_called_once_with(42)


def test_single_contact_runner_injects_only_selected_contact():
    captured = {}
    contact = {"id": 42, "name": "Acme", "deleted_at": None}

    class Agent:
        def invoke(self, state):
            captured["contacts"] = dependencies["fetch_contacts"](state["limit"])
            return {"summary": "saved"}

    dependencies = {}

    def create_agent(**kwargs):
        dependencies.update(kwargs)
        return Agent()

    with patch.object(contact_opportunity_analysis, "get_contact", return_value=contact), \
         patch.object(contact_opportunity_analysis, "get_llm"), \
         patch("gcrm_opportunity_agent.create_opportunity_agent", side_effect=create_agent):
        result = contact_opportunity_analysis.analyse_contact_opportunity(42)

    assert result["summary"] == "saved"
    assert captured["contacts"] == [contact]
