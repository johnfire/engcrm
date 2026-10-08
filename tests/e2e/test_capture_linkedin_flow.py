"""Card/page upload -> profile review -> persisted person and provenance."""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from gcrm.api.jwt_auth import create_token
from gcrm.api.main import app
from gcrm.db.connection import db
from gcrm.tools.db_people import save_person

pytestmark = pytest.mark.e2e
AUTH = {"Authorization": f"Bearer {create_token('admin')}", "X-Request-ID": "scan-profile"}
PROFILE = "https://www.linkedin.com/in/anna-roth"
FIELDS = {"company": "ACME", "name": "Anna Roth", "email": "anna@acme.test", "is_card": True}


def upload_capture(client, kind):
    if kind == "card":
        response = client.post("/api/cards", headers=AUTH, files={"image": ("card.jpg", b"photo", "image/jpeg")})
        return response.json()
    response = client.post("/api/documents", headers=AUTH, data={"capture_batch_id": "linkedin-page"},
                           files={"image": ("page.jpg", b"photo", "image/jpeg")})
    return response.json()["captures"][0]


@pytest.mark.parametrize("kind", ["card", "document"])
def test_scanned_person_profile_is_saved_only_after_review(clean_database, tmp_path, kind):
    client = TestClient(app)
    with patch("gcrm.tools.cards.CARD_IMAGE_DIR", str(tmp_path)), \
         patch("gcrm.tools.cards.extract_card_fields", return_value={"fields": FIELDS, "model": "test", "cost_usd": 0}), \
         patch("gcrm.tools.documents.extract_document_contacts", return_value={"contacts": [FIELDS], "model": "test", "cost_usd": 0}), \
         patch("gcrm.tools.capture_linkedin.DDGS") as search, \
         patch("gcrm.tools.cards.enrich_one"):
        search.return_value.text.return_value = [{"href": PROFILE, "title": "Anna Roth - ACME", "body": "Augsburg"}]
        capture = upload_capture(client, kind)
        capture_id = capture["capture_id"]
        endpoint = f"/api/cards/{capture_id}"
        suggestions = client.post(endpoint + "/linkedin-search", headers=AUTH,
                                  json={"name": "Anna Roth", "company": "ACME", "city": "Augsburg"})
        assert suggestions.status_code == 200
        assert suggestions.json()["candidates"][0]["url"] == PROFILE
        with db() as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT COUNT(*) AS total FROM people")
            assert cursor.fetchone()["total"] == 0
        confirmation = client.post(endpoint + "/confirm", headers=AUTH,
                                   json={"fields": {**capture["fields"], "linkedin_url": PROFILE}})
        assert confirmation.status_code == 200
    person_id = confirmation.json()["person_id"]
    person = client.get(f"/api/people/{person_id}", headers=AUTH).json()
    assert person["linkedin_url"] == PROFILE
    assert person["source"] == f"{kind}_capture"
    assert person["created_at"]
    assert not person["is_linkedin_contact"]
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT captured_at, captured_by, kind, extracted FROM card_captures WHERE id=%s", (capture_id,))
        captured = cursor.fetchone()
        assert captured["captured_at"] and captured["captured_by"] == "shared-admin"
        assert captured["kind"] == kind and captured["extracted"]["linkedin_url"] == PROFILE
        cursor.execute("SELECT actor, correlation_id, outcome FROM audit_log WHERE action='person.capture_confirmed' AND target=%s", (f"person:{person_id}",))
        assert dict(cursor.fetchone()) == {"actor": "shared-admin", "correlation_id": "scan-profile", "outcome": f"card_capture:{capture_id}"}


def test_existing_profile_conflict_keeps_scan_pending_and_original_source(clean_database, tmp_path):
    original = save_person("Anna Roth", email="anna@acme.test", source="manual")
    with db() as connection:
        connection.cursor().execute("UPDATE people SET linkedin_url=%s WHERE id=%s", (PROFILE, original))
    client = TestClient(app)
    with patch("gcrm.tools.cards.CARD_IMAGE_DIR", str(tmp_path)), \
         patch("gcrm.tools.cards.extract_card_fields", return_value={"fields": FIELDS, "model": "test", "cost_usd": 0}):
        capture = upload_capture(client, "card")
        confirmation = client.post(f"/api/cards/{capture['capture_id']}/confirm", headers=AUTH,
                                   json={"fields": {**FIELDS, "linkedin_url": "https://linkedin.com/in/different-anna"}})
    assert confirmation.status_code == 409
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT source, linkedin_url FROM people WHERE id=%s", (original,))
        assert dict(cursor.fetchone()) == {"source": "manual", "linkedin_url": PROFILE}
        cursor.execute("SELECT status FROM card_captures WHERE id=%s", (capture["capture_id"],))
        assert cursor.fetchone()["status"] == "pending_review"


def test_search_cannot_access_capture_in_another_workspace(clean_database):
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("INSERT INTO workspaces (name, slug) VALUES ('Foreign scans', 'foreign-scans') ON CONFLICT (slug) DO UPDATE SET name=EXCLUDED.name RETURNING id")
        workspace_id = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO card_captures (workspace_id) VALUES (%s) RETURNING id", (workspace_id,))
        capture_id = cursor.fetchone()["id"]
    with patch("gcrm.api.routers.api_capture_linkedin.find_capture_profiles") as search:
        response = TestClient(app).post(f"/api/cards/{capture_id}/linkedin-search", headers=AUTH, json={"name": "Anna Roth"})
    assert response.status_code == 404
    search.assert_not_called()


def test_lookup_outage_still_allows_contact_save_without_profile(clean_database, tmp_path):
    client = TestClient(app)
    with patch("gcrm.tools.cards.CARD_IMAGE_DIR", str(tmp_path)), \
         patch("gcrm.tools.cards.extract_card_fields", return_value={"fields": FIELDS, "model": "test", "cost_usd": 0}), \
         patch("gcrm.tools.capture_linkedin.DDGS", side_effect=RuntimeError("offline")), \
         patch("gcrm.tools.cards.enrich_one"):
        capture = upload_capture(client, "card")
        endpoint = f"/api/cards/{capture['capture_id']}"
        lookup = client.post(endpoint + "/linkedin-search", headers=AUTH, json={"name": "Anna Roth"})
        assert lookup.json() == {"status": "unavailable", "candidates": []}
        confirmation = client.post(endpoint + "/confirm", headers=AUTH, json={"fields": FIELDS})
        assert confirmation.status_code == 200
    person = client.get(f"/api/people/{confirmation.json()['person_id']}", headers=AUTH).json()
    assert person["linkedin_url"] is None
    assert person["source"] == "card_capture"
