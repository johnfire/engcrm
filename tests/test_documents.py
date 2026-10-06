"""Document extraction validation and upload guards, without live AI calls."""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from gcrm.api.jwt_auth import create_token
from gcrm.api.main import app
from gcrm.tools import documents

client = TestClient(app)
AUTH = {"Authorization": f"Bearer {create_token('admin')}"}


def test_document_contacts_preserve_rows_and_missing_values():
    contacts = documents.normalize_document_contacts({"contacts": [
        {"company": " ACME ", "name": "Ann", "email": "ann@acme.test", "confidence": 88},
        {"company": "Other", "phone": "01234", "confidence": 200},
    ]})
    assert len(contacts) == 2
    assert contacts[0]["company"] == "ACME"
    assert contacts[0]["email"] == "ann@acme.test"
    assert contacts[1]["email"] is None
    assert contacts[1]["confidence"] is None


@pytest.mark.parametrize("payload", [
    {}, [], {"contacts": {}}, {"contacts": ["name"]}, {"contacts": [{}]},
    {"contacts": [{"name": ["Ann"]}]}, {"contacts": [{"name": "Ann"}] * 51},
])
def test_malformed_document_responses_are_rejected(payload):
    with pytest.raises(ValueError):
        documents.normalize_document_contacts(payload)


def test_vision_extracts_multiple_contacts_and_records_cost():
    response = MagicMock()
    response.content = '{"contacts":[{"name":"Ann"},{"company":"Bakery"}],"note":null}'
    response.usage_metadata = {"input_tokens": 1500, "output_tokens": 200}
    response.response_metadata = {"stop_reason": "end_turn"}
    model = MagicMock()
    model.invoke.return_value = response
    with patch("gcrm.tools.llm.get_llm", return_value=model):
        extraction = documents.extract_document_contacts(b"photo")
    assert len(extraction["contacts"]) == 2
    assert extraction["cost_usd"] == 0.002


def test_truncated_vision_output_does_not_partially_import_a_page():
    response = MagicMock()
    response.content = '{"contacts":[{"name":"Ann"}]}'
    response.response_metadata = {"stop_reason": "max_tokens"}
    model = MagicMock()
    model.invoke.return_value = response
    with patch("gcrm.tools.llm.get_llm", return_value=model):
        extraction = documents.extract_document_contacts(b"photo")
    assert extraction["contacts"] == []
    assert extraction["note"] == documents.EXTRACTION_FAILED


@pytest.mark.parametrize("content_type, image, expected", [
    ("text/plain", b"text", 415), ("image/jpeg", b"", 400),
])
def test_document_upload_rejects_invalid_files(content_type, image, expected):
    response = client.post("/api/documents", headers=AUTH, data={"capture_batch_id": "page-1"},
                           files={"image": ("page.jpg", image, content_type)})
    assert response.status_code == expected


def test_document_upload_requires_admin_and_valid_batch_id():
    upload = {"image": ("page.jpg", b"photo", "image/jpeg")}
    assert client.post("/api/documents", files=upload, data={"capture_batch_id": "test"}).status_code in (401, 403)
    spectator = {"Authorization": f"Bearer {create_token('spectator')}"}
    assert client.post("/api/documents", headers=spectator, files=upload,
                       data={"capture_batch_id": "test"}).status_code == 403
    assert client.post("/api/documents", headers=AUTH, files=upload,
                       data={"capture_batch_id": "../bad"}).status_code == 422


def test_gps_is_sent_to_places_search_and_matched_city_is_used():
    from gcrm.tools import search, signs

    response = MagicMock()
    response.json.return_value = {"places": [{
        "id": "nearby", "displayName": {"text": "Bakery"},
        "location": {"latitude": 48.37, "longitude": 10.90},
        "addressComponents": [
            {"types": ["sublocality_level_1"], "longText": "Centre"},
            {"types": ["locality"], "longText": "Augsburg"},
            {"types": ["country"], "shortText": "DE"},
        ],
    }]}
    with patch("gcrm.config.GOOGLE_MAPS_API_KEY", "test"), patch.object(search.httpx, "post", return_value=response) as post:
        place = signs.resolve_business("Bakery", (48.37, 10.90))
    payload = post.call_args.kwargs["json"]
    assert payload["locationBias"]["circle"]["center"] == {"latitude": 48.37, "longitude": 10.90}
    assert "locationRestriction" not in payload
    assert place["city"] == "Augsburg"
    assert signs.build_organization_fields("Bakery", {}, place)["country"] == "DE"
