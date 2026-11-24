"""Follow-up forms operate on real database rows and preserve siblings."""
import pytest
from fastapi.testclient import TestClient

from gcrm.api.auth import require_admin, require_login
from gcrm.api.main import app
from gcrm.tools.db_organizations import save_organization
from gcrm.tools.db_people import save_person
from gcrm.tools.deal_records import get_deals
from gcrm.tools.follow_ups import list_follow_ups

pytestmark = pytest.mark.integration


def test_create_edit_and_complete_from_web(clean_database, monkeypatch):
    monkeypatch.setattr("gcrm.tools.db_organizations.geocode", lambda city, country: None)
    organization = save_organization("Example GmbH", "Augsburg", source="test_fixture")
    deal = get_deals("organization", organization)[0]
    app.dependency_overrides[require_login] = lambda: "admin"
    app.dependency_overrides[require_admin] = lambda: "admin"
    try:
        client = TestClient(app)
        for text in ("Send details", "Call later"):
            response = client.post("/follow-ups/new", data={"target": f"deal:{deal['id']}",
                "task_type": "commitment", "task_text": text}, follow_redirects=False)
            assert response.status_code == 303
        page = client.get("/follow-ups/?lang=en")
        assert page.status_code == 200
        assert "Send details" in page.text and "Call later" in page.text
        assert client.get("/follow-ups/?offer=&task_type=&date_from=&date_to=&direction=asc").status_code == 200
        first, second = list_follow_ups()
        response = client.post(f"/follow-ups/{first['id']}/edit", data={"task_type": "check_in",
            "task_text": "Send updated details", "version": first["updated_at"].isoformat()}, follow_redirects=False)
        assert response.status_code == 303
        first = list_follow_ups()[0]
        response = client.post(f"/follow-ups/{first['id']}/status", data={"status": "completed",
            "version": first["updated_at"].isoformat()}, follow_redirects=False)
        assert response.status_code == 303
        assert [task["id"] for task in list_follow_ups()] == [second["id"]]
    finally:
        app.dependency_overrides.pop(require_login, None)
        app.dependency_overrides.pop(require_admin, None)


def test_create_names_a_person_only_when_they_belong_to_the_organization(clean_database, monkeypatch):
    monkeypatch.setattr("gcrm.tools.db_organizations.geocode", lambda city, country: None)
    organization = save_organization("Example GmbH", "Augsburg", source="test_fixture")
    other = save_organization("Other GmbH", "Augsburg", source="test_fixture")
    anna = save_person("Anna Example", contact_id=organization, source="test_fixture", geocode_city=False)
    app.dependency_overrides[require_login] = lambda: "admin"
    app.dependency_overrides[require_admin] = lambda: "admin"
    try:
        client = TestClient(app)
        fields = {"target": f"organization:{organization}", "contact_person_id": str(anna),
                  "task_type": "commitment", "task_text": "Send Anna the specification"}
        assert client.post("/follow-ups/new", data=fields, follow_redirects=False).status_code == 303
        assert list_follow_ups()[0]["contact_person_id"] == anna
        fields["target"] = f"organization:{other}"
        assert client.post("/follow-ups/new", data=fields, follow_redirects=False).status_code == 400
    finally:
        app.dependency_overrides.pop(require_login, None)
        app.dependency_overrides.pop(require_admin, None)
