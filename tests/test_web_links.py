"""browsable_url normalisation plus the rendered "open website" links on the
person and contact detail pages. DB is mocked — runs without Postgres."""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import gcrm.api.main as main
from gcrm.api.auth import require_admin, require_login
from gcrm.api.web_links import browsable_url

client = TestClient(main.app)

PERSON_ROW = {
    "id": 3, "name": "Anna Roth", "title": "Kuratorin", "email": "anna@galerie-nord.de",
    "phone": "+49 821 555 12", "website": "galerie-nord.de", "city": "Augsburg", "country": "DE",
    "relationship": None, "notes": None, "met_at": None,
    "contact_id": 42, "company": "Galerie Nord", "source": "card_capture",
    "created_at": "2026-08-19T10:00:00+00:00",
}

CONTACT_ROW = {
    "id": 1, "name": "Acme GmbH", "city": "Augsburg", "country": "DE", "type": "Handwerksbetrieb",
    "status": "candidate", "email": "a@acme.de", "website": "acme.de", "fit_score": 80,
    "notes": None, "flagged": False, "starred": False, "personal_priority": None,
    "last_contact": None, "address": None, "phone": None, "source": None, "maps_uri": None,
    "created_at": "2026-08-19T10:00:00+00:00", "decision_maker": None,
    "preferred_contact_method": None, "best_visit_time": None, "visit_duration": None,
    "last_visited_at": None, "first_impression": None, "last_impression": None,
    "materials_left": None, "followup_promised": None, "space_notes": None,
    "access_notes": None, "price_sensitivity": None,
}


@pytest.fixture
def admin_web():
    main.app.dependency_overrides[require_login] = lambda: "admin"
    main.app.dependency_overrides[require_admin] = lambda: "admin"
    yield
    main.app.dependency_overrides.pop(require_login, None)
    main.app.dependency_overrides.pop(require_admin, None)


def mock_contact_page(contact):
    """A cursor that answers the contact detail route: the contact row, then
    its (absent) opportunity analysis, then an empty interaction list."""
    cur = MagicMock()
    cur.fetchone.side_effect = [contact, None]
    cur.fetchall.return_value = []
    conn = MagicMock()
    conn.cursor.return_value = cur
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    return conn


class TestBrowsableUrl:
    def test_keeps_a_full_url_as_typed(self):
        assert browsable_url("https://acme.de/kontakt") == "https://acme.de/kontakt"
        assert browsable_url("http://acme.de") == "http://acme.de"

    def test_assumes_https_when_the_scheme_is_missing(self):
        assert browsable_url("acme.de") == "https://acme.de"
        assert browsable_url("www.acme.de/team") == "https://www.acme.de/team"

    def test_trims_surrounding_whitespace(self):
        assert browsable_url("  acme.de\n") == "https://acme.de"

    @pytest.mark.parametrize("stored", [None, "", "   "])
    def test_returns_none_for_empty_values(self, stored):
        assert browsable_url(stored) is None

    @pytest.mark.parametrize("stored", [
        "javascript:alert(1)",
        "data:text/html,<script>alert(1)</script>",
        "mailto:anna@acme.de",
        "file:///etc/passwd",
    ])
    def test_refuses_schemes_a_browser_should_not_be_handed(self, stored):
        assert browsable_url(stored) is None

    @pytest.mark.parametrize("stored", ["acme", "https://localhost", "n/a"])
    def test_refuses_values_without_a_real_host(self, stored):
        assert browsable_url(stored) is None


class TestPersonDetailWebsiteLink:
    def test_links_a_scheme_less_website(self, admin_web):
        with patch("gcrm.api.routers.people.get_person", return_value=PERSON_ROW):
            response = client.get("/people/3")
        assert response.status_code == 200
        assert 'href="https://galerie-nord.de" target="_blank" rel="noopener noreferrer"' in response.text

    def test_offers_no_link_for_an_unusable_website(self, admin_web):
        person = {**PERSON_ROW, "website": "javascript:alert(1)"}
        with patch("gcrm.api.routers.people.get_person", return_value=person):
            response = client.get("/people/3")
        assert response.status_code == 200
        assert "field-open-link" not in response.text

    def test_offers_no_link_when_no_website_is_stored(self, admin_web):
        with patch("gcrm.api.routers.people.get_person", return_value={**PERSON_ROW, "website": None}):
            response = client.get("/people/3")
        assert response.status_code == 200
        assert "field-open-link" not in response.text


class TestContactDetailWebsiteLink:
    def test_links_a_scheme_less_website(self, admin_web):
        with patch("gcrm.api.routers.contacts.db") as mock_db:
            mock_db.return_value.__enter__.return_value = mock_contact_page(CONTACT_ROW)
            response = client.get("/contacts/1")
        assert response.status_code == 200
        assert 'href="https://acme.de" target="_blank" rel="noopener noreferrer"' in response.text

    def test_offers_no_link_for_an_unusable_website(self, admin_web):
        with patch("gcrm.api.routers.contacts.db") as mock_db:
            mock_db.return_value.__enter__.return_value = mock_contact_page(
                {**CONTACT_ROW, "website": "javascript:alert(1)"}
            )
            response = client.get("/contacts/1")
        assert response.status_code == 200
        assert "field-open-link" not in response.text
