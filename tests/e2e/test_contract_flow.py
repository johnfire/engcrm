"""One contract, end to end through real pages: made on an organization, opened from the Contracts list, given a link."""
import re
from datetime import date

import pytest
from fastapi.testclient import TestClient

import gcrm.api.main as main
from gcrm.api.security import hash_password
from gcrm.db.connection import db
from gcrm.tools.db_organizations import save_organization

pytestmark = pytest.mark.e2e
PASSWORD = "a-long-test-password-1"


def test_create_a_contract_on_an_organization_open_it_from_the_list_and_add_a_link(clean_database, monkeypatch):
    monkeypatch.setattr("gcrm.tools.db_organizations.geocode", lambda city, country: None)
    with db() as connection:
        connection.cursor().execute(
            "INSERT INTO users (email, name, password_hash, role, workspace_id, is_active) "
            "SELECT 'owner@first.example', 'owner', %s, 'admin', id, TRUE FROM workspaces WHERE slug = 'default'",
            (hash_password(PASSWORD),))
    school = save_organization("VHS Musterstadt", "Augsburg", source="test_fixture")
    browser = TestClient(main.app)
    assert browser.post("/login", data={"email": "owner@first.example", "password": PASSWORD}, follow_redirects=False).status_code == 303

    organization = browser.get(f"/organizations/{school}?lang=en").text
    assert "New contract" in organization
    made = browser.post(f"/organizations/{school}/sales", follow_redirects=False,
                        data={"title": "AI course for Kaufleute", "kind": "teaching_course", "amount_eur": "2400",
                              "won_on": date.today().isoformat(), "status": "booked"})
    assert made.status_code == 303

    listed = browser.get("/contracts/?lang=en").text
    href = re.search(r'<a class="contract-title" href="(/contracts/\d+)">AI course for Kaufleute</a>', listed).group(1)
    page = browser.get(href).text
    assert "AI course for Kaufleute" in page and "VHS Musterstadt" in page

    added = browser.post(f"{href}/links", data={"label": "Syllabus", "url": "https://example.org/syllabus"}, follow_redirects=False)
    assert added.status_code == 303 and added.headers["location"] == href
    assert '<a href="https://example.org/syllabus" target="_blank" rel="noopener noreferrer">Syllabus</a>' in browser.get(href).text
