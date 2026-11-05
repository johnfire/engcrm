"""A named person met at a company survives saving and appears in contact views."""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from gcrm.api.auth import hash_password
from gcrm.api.main import app
from gcrm.db.connection import db
from gcrm.tools.db_users import create_user

pytestmark = pytest.mark.e2e


@pytest.fixture
def company_browser(clean_database):
    password = "company-people-test-password"
    create_user("company-people@example.test", hash_password(password), "admin")
    browser = TestClient(app)
    assert browser.post("/login", data={"email": "company-people@example.test", "password": password},
                        follow_redirects=False).status_code == 303
    with patch("gcrm.api.routers.api_record_edit.geocode", return_value=None), \
         patch("gcrm.tools.db_organizations.geocode", return_value=None):
        created = browser.post("/organizations/new", data={
            "name": "Trust in Soda", "city": "Lucerne", "country": "CH", "offer": "consulting",
            "pipeline_stage": "suspect", "decision_maker": "Bruno Healy",
        }, follow_redirects=False)
    assert created.status_code == 303
    return browser, int(created.headers["location"].split("/")[-1])


def test_company_add_person_creates_a_linked_contact_once(company_browser):
    browser, company_id = company_browser
    company_page = browser.get(f"/organizations/{company_id}")
    assert f'href="/people/new?contact_id={company_id}"' in company_page.text
    form = browser.get("/people/new", params={"contact_id": company_id})
    assert form.status_code == 200
    assert f'value="{company_id}" selected' in form.text
    assert 'name="spoke_today"' in form.text
    typed = {"name": " Bruno Healy ", "contact_id": company_id, "spoke_today": "true"}
    with patch("gcrm.tools.db_people.geocode", return_value=None):
        saved = browser.post("/people/new", data=typed, follow_redirects=False,
                             headers={"X-Request-ID": "company-person-save"})
    assert saved.status_code == 303
    person_page = browser.get(saved.headers["location"])
    assert "Bruno Healy" in person_page.text and "Saved" in person_page.text
    assert f'href="/organizations/{company_id}"' in person_page.text
    assert "Bruno Healy" in browser.get(f"/organizations/{company_id}").text
    assert "Bruno Healy" in browser.get("/people/?offer=all").text
    contacts = browser.get("/contact-feed/?offer=all").text
    assert "Trust in Soda" in contacts and "Bruno Healy" in contacts
    repeated = browser.post("/people/new", data=typed, follow_redirects=False)
    assert repeated.status_code == 409
    assert 'name="contact_id"' in repeated.text and 'name="spoke_today"' in repeated.text
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id, city, country FROM people WHERE contact_id=%s", (company_id,))
        people = cursor.fetchall()
        assert len(people) == 1 and people[0]["city"] == "Lucerne" and people[0]["country"] == "CH"
        cursor.execute("SELECT count(*) AS total FROM people_interactions WHERE person_id=%s", (people[0]["id"],))
        assert cursor.fetchone()["total"] == 1
        cursor.execute("SELECT actor, correlation_id FROM audit_log WHERE action='person.created' AND target=%s",
                       (f"person:{people[0]['id']}",))
        audit = cursor.fetchone()
        assert audit["actor"] != "system-job" and audit["correlation_id"] == "company-person-save"


def test_choose_existing_person_links_without_duplicating_or_moving_other_contacts(company_browser):
    browser, company_id = company_browser
    person = browser.post("/people/new", data={"name": "Bruno Healy"}, follow_redirects=False)
    person_id = int(person.headers["location"].split("/")[-1].split("?")[0])
    choices = browser.get("/people/new", params={"contact_id": company_id, "q": "Bruno"})
    assert f'value="{person_id}"' in choices.text
    linked = browser.post("/people/link-existing", data={
        "person_id": person_id, "contact_id": company_id, "spoke_today": "true",
    }, follow_redirects=False)
    assert linked.status_code == 303
    assert "Bruno Healy" in browser.get(f"/organizations/{company_id}").text
    browser.post("/people/link-existing", data={"person_id": person_id, "contact_id": company_id,
                                               "spoke_today": "true"}, follow_redirects=False)
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT count(*) AS total FROM people WHERE name='Bruno Healy'")
        assert cursor.fetchone()["total"] == 1
        cursor.execute("SELECT count(*) AS total FROM people_interactions WHERE person_id=%s", (person_id,))
        assert cursor.fetchone()["total"] == 1


def test_invalid_company_preserves_the_form_without_saving(company_browser):
    browser, _ = company_browser
    refused = browser.post("/people/new", data={"name": "Bruno Healy", "contact_id": 999999},
                           follow_redirects=False)
    assert refused.status_code == 400
    assert 'value="Bruno Healy"' in refused.text
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT count(*) AS total FROM people")
        assert cursor.fetchone()["total"] == 0
