"""Backdate a contact on the website, then see corrected mobile history and order."""
import pytest
from fastapi.testclient import TestClient

from gcrm.api.main import app
from gcrm.api.security import hash_password
from gcrm.tools.db_users import create_user

pytestmark = pytest.mark.e2e


def test_website_and_mobile_share_backdated_contacts_and_reject_stale_changes(clean_database, monkeypatch):
    monkeypatch.setattr("gcrm.tools.db_organizations.geocode", lambda city, country: None)
    monkeypatch.setattr("gcrm.tools.db_people.geocode", lambda city, country: None)
    password = "contact-date-flow-password"
    create_user("dates@example.test", hash_password(password), "admin")
    browser = TestClient(app)
    token = browser.post("/api/auth/token", json={"email": "dates@example.test", "password": password}).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    company_id = browser.post("/api/contacts", headers=headers, json={"name": "Academy"}).json()["id"]
    person_id = browser.post("/api/people", headers=headers, json={"name": "Ann"}).json()["id"]
    company = browser.patch(f"/api/contact-feed/organization/{company_id}/date", headers=headers,
                            json={"contact_date": "2026-10-03"}).json()
    person = browser.patch(f"/api/contact-feed/person/{person_id}/date", headers=headers,
                           json={"contact_date": "2026-10-04"}).json()
    assert browser.get("/api/contact-feed", headers=headers).json()[0]["kind"] == "person"
    browser.post("/login", data={"email": "dates@example.test", "password": password})
    editor_url = f"/contact-feed/person/{person_id}/date"
    assert 'value="2026-10-04"' in browser.get(editor_url).text
    correction = browser.post(editor_url, data={"contact_date": "2026-10-02", "interaction_id": person["interaction_id"],
                              "previous_date": person["contact_date"]}, follow_redirects=False)
    assert correction.status_code == 303
    feed = browser.get("/api/contact-feed", headers=headers).json()
    assert [(contact["name"], contact["last_contact"]) for contact in feed] == [("Academy", "2026-10-03"), ("Ann", "2026-10-02")]
    assert browser.get(f"/api/people/{person_id}/notes", headers=headers).json()[0]["occurred_at"][:10] == "2026-10-02"
    stale = browser.patch(f"/api/contact-feed/organization/{company_id}/date", headers=headers,
                          json={"contact_date": "2026-10-01", "interaction_id": company["interaction_id"], "previous_date": "2026-10-02"})
    assert stale.status_code == 409
    assert browser.get("/api/contact-feed", headers=headers).json() == feed
