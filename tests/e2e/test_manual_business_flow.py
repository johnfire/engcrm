"""Website form and mobile creation both feed the latest contacts list."""
import pytest
from fastapi.testclient import TestClient

from gcrm.api.main import app
from gcrm.api.security import hash_password
from gcrm.tools.db_users import create_user

pytestmark = pytest.mark.e2e


def test_add_business_on_web_and_mobile_then_find_it_in_contacts(clean_database, monkeypatch):
    monkeypatch.setattr("gcrm.tools.db_organizations.geocode", lambda city, country: None)
    password = "manual-business-password"
    create_user("manual@example.test", hash_password(password), "admin")
    browser = TestClient(app)
    assert browser.post("/login", data={"email": "manual@example.test", "password": password},
                        follow_redirects=False).status_code == 303
    assert 'href="/organizations/new"' in browser.get("/contact-feed/").text
    assert 'href="/organizations/new"' in browser.get("/organizations/").text
    assert browser.get("/organizations/new").status_code == 200
    saved = browser.post("/organizations/new", data={"name": "Web Academy", "city": "Augsburg",
                         "email": "web@academy.test", "pipeline_stage": "opportunity", "notes": "From website"},
                         follow_redirects=False)
    assert saved.status_code == 303
    assert "Web Academy" in browser.get(saved.headers["location"]).text
    duplicate = browser.post("/organizations/new", data={"name": "Web Academy", "city": "Augsburg"})
    assert duplicate.status_code == 409 and "Open existing business" in duplicate.text
    token = browser.post("/api/auth/token", json={"email": "manual@example.test", "password": password}).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    mobile = browser.post("/api/contacts", headers=headers, json={"name": "Mobile Academy", "pipeline_stage": "customer"})
    assert mobile.status_code == 200
    assert browser.get("/api/contact-feed", headers=headers).json() == []
    web_id = int(saved.headers["location"].split("/")[-1])
    for contact_id, day in [(web_id, "2026-10-03"), (mobile.json()["id"], "2026-10-04")]:
        assert browser.patch(f"/api/contact-feed/organization/{contact_id}/date", headers=headers,
                             json={"contact_date": day}).status_code == 200
    contacts = browser.get("/api/contact-feed", headers=headers).json()
    assert [(contact["name"], contact["pipeline_stage"]) for contact in contacts] == [
        ("Mobile Academy", "customer"), ("Web Academy", "opportunity"),
    ]
    assert "Mobile Academy" in browser.get("/contact-feed/").text
    detail = browser.get(f"/api/contacts/{mobile.json()['id']}", headers=headers).json()
    assert detail["pipeline_stage"] == "customer"


def test_viewer_cannot_add_business_on_either_platform(clean_database):
    password = "viewer-business-password"
    create_user("viewer@example.test", hash_password(password), "spectator")
    browser = TestClient(app)
    browser.post("/login", data={"email": "viewer@example.test", "password": password})
    assert 'href="/organizations/new"' not in browser.get("/contact-feed/").text
    assert browser.get("/organizations/new").status_code == 403
    assert browser.post("/organizations/new", data={"name": "Forbidden"}).status_code == 403
    token = browser.post("/api/auth/token", json={"email": "viewer@example.test", "password": password}).json()["token"]
    assert browser.post("/api/contacts", json={"name": "Forbidden"}, headers={"Authorization": f"Bearer {token}"}).status_code == 403
