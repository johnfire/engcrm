"""Website person forms preserve the company and user input across all save outcomes."""
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from gcrm.api.auth import require_admin, require_login
from gcrm.api.main import app
from gcrm.tools.db_people import save_person
from gcrm.tools.web_person_capture import ExistingPerson

COMPANY = {"id": 1583, "name": "Trust in Soda", "city": "Lucerne", "country": "CH"}
CHOICES = {"organizations": [COMPANY], "organization": COMPANY, "person_matches": []}


@pytest.fixture
def browser():
    app.dependency_overrides[require_login] = lambda: "admin"
    app.dependency_overrides[require_admin] = lambda: "admin"
    with patch("gcrm.api.routers.people.capture_choices", return_value=CHOICES):
        yield TestClient(app)
    app.dependency_overrides.pop(require_login, None)
    app.dependency_overrides.pop(require_admin, None)


def test_company_form_labels_and_selected_company_are_visible(browser):
    response = browser.get("/people/new?contact_id=1583")
    assert response.status_code == 200
    assert "Contact person at Trust in Soda" in response.text
    assert 'value="1583" selected' in response.text
    assert "[common.company]" not in response.text
    assert 'name="spoke_today" value="true"' in response.text


def test_company_and_conversation_reach_the_transactional_writer(browser):
    with patch("gcrm.api.routers.people.save_company_person", return_value=17) as save:
        response = browser.post("/people/new", data={"name": " Bruno Healy ", "contact_id": 1583,
                                                   "spoke_today": "true"}, follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/people/17?saved=1"
    fields, company, stage, offer, duplicate, spoke_today = save.call_args.args
    assert fields["name"] == "Bruno Healy" and fields["country"] is None
    assert (company, stage, offer, duplicate, spoke_today) == (1583, "", "consulting", False, True)


@pytest.mark.parametrize("failure,status", [(ValueError("Organization not found"), 400),
                                          (RuntimeError("write unavailable"), 503)])
def test_failed_save_preserves_name_company_and_spoken_checkbox(browser, failure, status):
    with patch("gcrm.api.routers.people.save_company_person", side_effect=failure), \
         patch("gcrm.api.routers.people.log_audit") as audit:
        response = browser.post("/people/new", data={"name": "Bruno Healy", "contact_id": 1583,
                                                   "spoke_today": "true"})
    assert response.status_code == status
    assert 'value="Bruno Healy"' in response.text and 'value="1583" selected' in response.text
    assert 'name="spoke_today" value="true" checked' in response.text
    audit.assert_not_called()


def test_duplicate_opens_existing_without_claiming_a_successful_save(browser):
    with patch("gcrm.api.routers.people.save_company_person", side_effect=ExistingPerson(17)), \
         patch("gcrm.api.routers.people.get_person", return_value={"id": 17, "name": "Bruno Healy"}):
        response = browser.post("/people/new", data={"name": "Bruno Healy", "contact_id": 1583})
    assert response.status_code == 409
    assert 'href="/people/17"' in response.text
    assert "Nothing was saved yet" in response.text


def test_existing_selection_links_the_chosen_person(browser):
    with patch("gcrm.api.routers.people.link_existing_person") as link:
        response = browser.post("/people/link-existing", data={"person_id": 17, "contact_id": 1583,
                                                             "spoke_today": "true"}, follow_redirects=False)
    link.assert_called_once_with(17, 1583, True)
    assert response.headers["location"] == "/people/17?saved=1"


def test_read_only_access_cannot_link_a_person(browser):
    def refuse_write():
        raise HTTPException(403, "Admin only")
    app.dependency_overrides[require_admin] = refuse_write
    with patch("gcrm.api.routers.people.link_existing_person") as link:
        response = browser.post("/people/link-existing", data={"person_id": 17, "contact_id": 1583})
    assert response.status_code == 403
    link.assert_not_called()


def test_failed_existing_link_keeps_the_selected_person_and_search(browser):
    choices = {**CHOICES, "person_matches": [{"id": 17, "name": "Bruno Healy", "email": None}]}
    with patch("gcrm.api.routers.people.capture_choices", return_value=choices), \
         patch("gcrm.api.routers.people.link_existing_person", side_effect=RuntimeError()):
        response = browser.post("/people/link-existing", data={
            "person_id": 17, "contact_id": 1583, "q": "Bruno", "spoke_today": "true",
        })
    assert response.status_code == 503
    assert 'value="Bruno"' in response.text and 'value="17" selected' in response.text
    assert 'name="spoke_today" value="true" checked' in response.text


def test_missing_company_in_form_does_not_silently_become_unlinked(browser):
    with patch("gcrm.api.routers.people.capture_choices", return_value={**CHOICES, "organization": None}):
        response = browser.get("/people/new?contact_id=999999")
    assert response.status_code == 400 and "Organization not found" in response.text


def test_company_lookup_failure_preserves_typed_values(browser):
    with patch("gcrm.api.routers.people.save_company_person", side_effect=RuntimeError()), \
         patch("gcrm.api.routers.people.capture_choices", side_effect=RuntimeError()):
        response = browser.post("/people/new", data={"name": "Bruno Healy", "contact_id": 1583})
    assert response.status_code == 503 and 'value="Bruno Healy"' in response.text
    assert "Company choices are temporarily unavailable" in response.text
    assert '<option value="1583" selected>' in response.text


def test_person_writer_joins_the_existing_transaction():
    cursor = MagicMock()
    cursor.fetchone.side_effect = [None, {"id": 17}]
    with patch("gcrm.tools.db_people.db") as database:
        person_id = save_person("Bruno Healy", source="manual_web", contact_id=1583, cursor=cursor)
    assert person_id == 17
    database.assert_not_called()
    assert "INSERT INTO people" in cursor.execute.call_args.args[0]
    assert cursor.execute.call_args.args[1][10] == 1583


def test_inherited_company_city_does_not_need_an_external_lookup():
    cursor = MagicMock()
    cursor.fetchone.side_effect = [None, {"id": 17}]
    with patch("gcrm.tools.db_people.geocode", return_value=None) as geocode:
        person_id = save_person("Bruno Healy", source="manual_web", contact_id=1583, cursor=cursor,
                                city="Lucerne", country="CH", geocode_city=False)
    assert person_id == 17
    geocode.assert_not_called()
    assert cursor.execute.call_args.args[1][5:7] == ("Lucerne", "CH")
