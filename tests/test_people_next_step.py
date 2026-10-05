"""A person's next step on the web page, the People list and the phone API.
The logging itself runs against Postgres in tests/integration/test_people_next_step_db.py."""
from datetime import date
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import gcrm.api.main as main
from gcrm.api.auth import require_admin, require_login
from gcrm.api.jwt_auth import create_token
from gcrm.tools.people_next_step import log_entry

client = TestClient(main.app)
ADMIN = {"Authorization": f"Bearer {create_token('admin')}"}
SPECTATOR = {"Authorization": f"Bearer {create_token('spectator')}"}
PERSON = {
    "id": 3, "name": "Anna Roth", "title": None, "email": None, "phone": None, "website": None,
    "city": "Augsburg", "country": "DE", "relationship": None, "notes": None, "met_at": None,
    "contact_id": None, "company": None, "source": "manual", "created_at": "2026-08-19T10:00:00+00:00",
    "distance_km": None, "pipeline_stage": None, "next_step": "Invite to coffee",
    "next_step_date": "2020-01-31",
}


@pytest.fixture
def admin_web():
    main.app.dependency_overrides[require_login] = lambda: "admin"
    main.app.dependency_overrides[require_admin] = lambda: "admin"
    yield
    main.app.dependency_overrides.pop(require_login, None)
    main.app.dependency_overrides.pop(require_admin, None)


def test_the_log_entry_carries_the_date_when_there_is_one():
    assert log_entry("Call", date(2026, 10, 15)) == "Call (2026-10-15)"
    assert log_entry("Call", None) == "Call"


class TestWebForm:
    def post(self, data, result=None):
        with patch("gcrm.api.routers.people.set_person_next_step", return_value=result) as setter:
            response = client.post("/people/3/next-step", data=data, follow_redirects=False)
        return response, setter

    def test_saving_sets_the_step_and_date_and_returns_to_the_person(self, admin_web):
        response, setter = self.post({"next_step": "Invite to coffee", "next_step_date": "2026-10-15"},
                                     result={"logged": True})
        assert response.status_code == 303 and response.headers["location"].startswith("/people/3")
        setter.assert_called_once_with(3, "Invite to coffee", date(2026, 10, 15))

    def test_done_clears_the_step_whatever_the_fields_say(self, admin_web):
        _, setter = self.post({"next_step": "Invite to coffee", "next_step_date": "2026-10-15", "done": "1"},
                              result={"logged": True})
        setter.assert_called_once_with(3, "", None)

    def test_a_bad_date_is_refused(self, admin_web):
        response, setter = self.post({"next_step": "x", "next_step_date": "15.10.2026"})
        assert response.status_code == 400
        setter.assert_not_called()

    def test_an_unknown_person_is_a_404(self, admin_web):
        response, _ = self.post({"next_step": "x"}, result=None)
        assert response.status_code == 404


class TestPages:
    def test_the_person_page_shows_the_step_overdue_and_labels_the_log(self, admin_web):
        log = [{"id": 1, "occurred_at": "2026-10-05T10:00:00", "method": "next_step",
                "note": "Invite to coffee (2020-01-31)"}]
        with patch("gcrm.api.routers.people.get_person", return_value=PERSON), \
             patch("gcrm.api.routers.people.get_person_interactions", return_value=log):
            response = client.get("/people/3?lang=en")
        assert response.status_code == 200, response.text[:400]
        assert 'action="/people/3/next-step"' in response.text
        assert "<strong>Invite to coffee</strong>" in response.text
        assert "next-step__due--overdue" in response.text and "overdue" in response.text
        assert 'name="done" value="1"' in response.text
        assert '<td class="muted">Next step</td>' in response.text

    def test_the_people_list_has_a_sortable_next_step_column(self, admin_web):
        with patch("gcrm.api.routers.people.get_people", return_value=[PERSON]) as listing, \
             patch("gcrm.api.routers.people.get_person_cities", return_value=[]):
            response = client.get("/people/?sort=next_step_date&dir=asc&lang=en")
        assert response.status_code == 200, response.text[:400]
        assert "sort=next_step_date" in response.text
        assert "Invite to coffee" in response.text and "next-step__due--overdue" in response.text
        assert listing.call_args.args[1:3] == ("next_step_date", "asc")


class TestPhoneApi:
    def test_admin_sets_the_step(self):
        result = {"next_step": "Call", "next_step_date": date(2026, 10, 15), "logged": True}
        with patch("gcrm.api.routers.api_people.set_person_next_step", return_value=result) as setter:
            response = client.put("/api/people/3/next-step", headers=ADMIN,
                                  json={"next_step": "Call", "next_step_date": "2026-10-15"})
        assert response.status_code == 200
        assert response.json() == {"next_step": "Call", "next_step_date": "2026-10-15", "logged": True}
        setter.assert_called_once_with(3, "Call", date(2026, 10, 15))

    def test_null_clears_it(self):
        result = {"next_step": None, "next_step_date": None, "logged": True}
        with patch("gcrm.api.routers.api_people.set_person_next_step", return_value=result) as setter:
            client.put("/api/people/3/next-step", headers=ADMIN, json={"next_step": None})
        setter.assert_called_once_with(3, "", None)

    def test_a_spectator_cannot_change_it(self):
        with patch("gcrm.api.routers.api_people.set_person_next_step") as setter:
            response = client.put("/api/people/3/next-step", headers=SPECTATOR, json={"next_step": "x"})
        assert response.status_code == 403
        setter.assert_not_called()

    def test_a_date_without_a_step_is_a_400(self):
        with patch("gcrm.api.routers.api_people.set_person_next_step", side_effect=ValueError("needs a step")):
            response = client.put("/api/people/3/next-step", headers=ADMIN, json={"next_step_date": "2026-10-15"})
        assert response.status_code == 400
