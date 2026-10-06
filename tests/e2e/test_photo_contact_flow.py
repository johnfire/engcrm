"""Photo -> persisted drafts -> review -> organization/person -> enrichment."""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from gcrm.api.jwt_auth import create_token
from gcrm.api.main import app
from gcrm.db.connection import db

pytestmark = pytest.mark.e2e
AUTH = {"Authorization": f"Bearer {create_token('admin')}", "X-Request-ID": "e2e-page"}


def upload_page(client):
    return client.post("/api/documents", headers=AUTH, data={"capture_batch_id": "same-page"},
                       files={"image": ("page.jpg", b"jpeg-photo", "image/jpeg")})


def test_page_contacts_are_reviewed_independently_and_retries_reuse_drafts(clean_database, tmp_path):
    client = TestClient(app)
    extraction = {"contacts": [
        {"company": "ACME", "name": "Ann", "email": "ann@example.test", "city": "Augsburg", "confidence": 90},
        {"company": "Bakery", "name": "Ben", "email": "ben@example.test", "city": "Munich", "confidence": 80},
    ], "model": "test", "cost_usd": 0.002}
    with patch("gcrm.tools.cards.CARD_IMAGE_DIR", str(tmp_path)), \
         patch("gcrm.tools.documents.extract_document_contacts", return_value=extraction) as vision:
        first = upload_page(client)
        retry = upload_page(client)
        assert first.status_code == retry.status_code == 200
        captures = first.json()["captures"]
        assert len(captures) == 2
        assert retry.json()["captures"] == captures
        vision.assert_called_once()
        assert len(list(tmp_path.glob("*.jpg"))) == 2
        queue = client.get("/api/cards", headers=AUTH).json()
        assert {draft["kind"] for draft in queue} == {"document"}
        assert len(queue) == 2
        with patch("gcrm.tools.cards.enrich_one") as enrichment:
            for capture in captures:
                confirmation = client.post(f"/api/cards/{capture['capture_id']}/confirm", headers=AUTH,
                                           json={"fields": capture["fields"]})
                assert confirmation.status_code == 200
            assert enrichment.call_count == 2
        duplicate_save = client.post(f"/api/cards/{captures[0]['capture_id']}/confirm", headers=AUTH,
                                     json={"fields": captures[0]["fields"]})
        assert duplicate_save.status_code == 409
    assert client.get("/api/cards", headers=AUTH).json() == []
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT name, source FROM contacts ORDER BY name")
        assert [(row["name"], row["source"]) for row in cursor.fetchall()] == [
            ("ACME", "document_capture"), ("Bakery", "document_capture"),
        ]
        cursor.execute("SELECT name, source, contact_id FROM people ORDER BY name")
        people = cursor.fetchall()
        assert [row["name"] for row in people] == ["Ann", "Ben"]
        assert all(row["source"] == "document_capture" and row["contact_id"] for row in people)
        cursor.execute("SELECT actor, correlation_id FROM audit_log WHERE action='document.captured'")
        assert all(row["actor"] == "shared-admin" and row["correlation_id"] == "e2e-page" for row in cursor.fetchall())


def test_sign_photo_gps_match_and_research_flow(clean_database, tmp_path):
    client = TestClient(app)
    place = {"name": "Bakery", "place_id": "nearby", "city": "Augsburg", "country": "DE", "address": "Main 1"}
    with patch("gcrm.tools.cards.CARD_IMAGE_DIR", str(tmp_path)), \
         patch("gcrm.tools.signs.extract_sign_fields", return_value={
             "fields": {"is_sign": True, "business_name": "Bakery"}, "model": "test", "cost_usd": 0,
         }), patch("gcrm.tools.signs.resolve_business", return_value=place) as resolution:
        response = client.post("/api/signs", headers=AUTH, data={"gps_lat": "48.37", "gps_lng": "10.90"},
                               files={"image": ("sign.jpg", b"photo", "image/jpeg")})
    assert response.status_code == 200
    resolution.assert_called_once_with("Bakery", (48.37, 10.90))
    capture_id = response.json()["capture_id"]
    wrong_mode = client.post(f"/api/cards/{capture_id}/confirm", headers=AUTH, json={"fields": {"company": "Bad"}})
    assert wrong_mode.status_code == 404
    with patch("gcrm.tools.signs.research_business") as research:
        confirmation = client.post(f"/api/signs/{capture_id}/confirm", headers=AUTH,
                                   json={"business_name": "Bakery", "accept_place": True})
        assert confirmation.status_code == 200
        research.assert_called_once_with(confirmation.json()["contact_id"])
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT city, source FROM contacts")
        assert dict(cursor.fetchone()) == {"city": "Augsburg", "source": "sign_scan"}


def test_document_person_failure_preserves_draft_for_retry(clean_database, tmp_path):
    client = TestClient(app)
    extraction = {"contacts": [{"company": "ACME", "name": "Ann", "email": "ann@example.test"}],
                  "model": "test", "cost_usd": 0}
    with patch("gcrm.tools.cards.CARD_IMAGE_DIR", str(tmp_path)), \
         patch("gcrm.tools.documents.extract_document_contacts", return_value=extraction):
        capture = upload_page(client).json()["captures"][0]
        endpoint = f"/api/cards/{capture['capture_id']}/confirm"
        with patch("gcrm.tools.cards.promote_to_person", side_effect=RuntimeError("unavailable")):
            failure = client.post(endpoint, headers=AUTH, json={"fields": capture["fields"]})
        assert failure.status_code == 503
        assert len(client.get("/api/cards", headers=AUTH).json()) == 1
        with patch("gcrm.tools.cards.enrich_one"):
            retry = client.post(endpoint, headers=AUTH, json={"fields": capture["fields"]})
        assert retry.status_code == 200
        assert retry.json()["person_id"]
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT count(*) AS count FROM contacts")
        assert cursor.fetchone()["count"] == 1


def test_discarding_one_document_row_keeps_the_other_photo(clean_database, tmp_path):
    client = TestClient(app)
    extraction = {"contacts": [{"company": "First"}, {"company": "Second"}], "model": "test", "cost_usd": 0}
    with patch("gcrm.tools.cards.CARD_IMAGE_DIR", str(tmp_path)), \
         patch("gcrm.tools.documents.extract_document_contacts", return_value=extraction):
        captures = upload_page(client).json()["captures"]
        first_id = captures[0]["capture_id"]
        assert client.post(f"/api/cards/{first_id}/discard", headers=AUTH).status_code == 200
        assert not (tmp_path / f"{first_id}.jpg").exists()
        assert (tmp_path / f"{captures[1]['capture_id']}.jpg").exists()
        assert len(client.get("/api/cards", headers=AUTH).json()) == 1
        confirmation = client.post(f"/api/cards/{first_id}/confirm", headers=AUTH, json={"fields": {"company": "First"}})
        assert confirmation.status_code == 409


def test_multiple_people_at_one_company_without_a_city_share_the_organization(clean_database, tmp_path):
    client = TestClient(app)
    extraction = {"contacts": [{"company": "ACME", "name": "Ann"}, {"company": "ACME", "name": "Ben"}],
                  "model": "test", "cost_usd": 0}
    with patch("gcrm.tools.cards.CARD_IMAGE_DIR", str(tmp_path)), \
         patch("gcrm.tools.documents.extract_document_contacts", return_value=extraction), \
         patch("gcrm.tools.cards.enrich_one"):
        captures = upload_page(client).json()["captures"]
        confirmations = [client.post(f"/api/cards/{capture['capture_id']}/confirm", headers=AUTH,
                                     json={"fields": capture["fields"]}) for capture in captures]
    assert all(confirmation.status_code == 200 for confirmation in confirmations)
    assert confirmations[0].json()["contact_id"] == confirmations[1].json()["contact_id"]
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT name, contact_id FROM people ORDER BY name")
        people = cursor.fetchall()
        assert [person["name"] for person in people] == ["Ann", "Ben"]
        assert people[0]["contact_id"] == people[1]["contact_id"]
