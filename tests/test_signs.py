"""Storefront-sign capture: vision extraction, Places resolution, contact-field
shaping, key-people lookup/promotion, and the capture/confirm endpoints. DB,
the vision LLM, and Places are mocked — these run without Postgres, a live
Anthropic key, or a live Google Maps key."""
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

import gcrm.api.main as main
from gcrm.api.jwt_auth import create_token
from gcrm.tools import signs

client = TestClient(main.app)
AUTH = {"Authorization": f"Bearer {create_token('admin')}"}


def make_mock_conn(rows=None):
    cur = MagicMock()
    cur.fetchone.return_value = rows[0] if rows else None
    cur.fetchall.return_value = rows or []
    conn = MagicMock()
    conn.cursor.return_value = cur
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    return conn, cur


class TestExtraction:
    def test_extract_parses_and_costs(self):
        resp = MagicMock()
        resp.content = '{"is_sign": true, "confidence": 85, "business_name": "Bäckerei Roth"}'
        resp.usage_metadata = {"input_tokens": 1500, "output_tokens": 200}
        fake_llm = MagicMock()
        fake_llm.invoke.return_value = resp
        with patch("gcrm.tools.llm.get_llm", return_value=fake_llm):
            out = signs.extract_sign_fields(b"\xff\xd8\xff-fake-jpeg")
        assert out["fields"]["business_name"] == "Bäckerei Roth"
        assert out["model"] == "claude-haiku-4-5-20251001"
        assert abs(out["cost_usd"] - 0.002) < 1e-6

    def test_extract_handles_failure(self):
        fake_llm = MagicMock()
        fake_llm.invoke.side_effect = RuntimeError("boom")
        with patch("gcrm.tools.llm.get_llm", return_value=fake_llm):
            out = signs.extract_sign_fields(b"x")
        assert out["fields"]["is_sign"] is False
        assert out["cost_usd"] == 0.0
        # The upstream message is logged, never handed to the client: it can
        # carry request URLs and model wiring. Only the fixed string goes out.
        assert out["fields"]["error"] == signs._EXTRACTION_FAILED
        assert "boom" not in out["fields"]["error"]


class TestResolveBusiness:
    def test_no_name_returns_none(self):
        assert signs.resolve_business("") is None

    def test_no_results_returns_none(self):
        with patch("gcrm.tools.search.google_maps_search", return_value=[]):
            assert signs.resolve_business("Ghost Shop") is None

    def test_no_key_degrades_to_none(self):
        # google_maps_search itself returns [] when GOOGLE_MAPS_API_KEY is unset —
        # resolve_business must not raise, just report unresolved.
        with patch("gcrm.tools.search.google_maps_search", return_value=[]):
            assert signs.resolve_business("Bäckerei Roth", gps=(48.37, 10.90)) is None

    def test_picks_nearest_result_when_gps_given(self):
        far = {"name": "Bäckerei Roth", "place_id": "far", "address": "", "city": "",
               "website": "", "phone": "", "latitude": 50.0, "longitude": 10.0, "google_data": {}}
        near = {"name": "Bäckerei Roth", "place_id": "near", "address": "Hauptstr 1", "city": "Augsburg",
                "website": "https://roth.de", "phone": "+49 821 1", "latitude": 48.371, "longitude": 10.898,
                "google_data": {}}
        with patch("gcrm.tools.search.google_maps_search", return_value=[far, near]):
            place = signs.resolve_business("Bäckerei Roth", gps=(48.37, 10.90))
        assert place["place_id"] == "near"
        assert place["city"] == "Augsburg"

    def test_no_gps_takes_first_result(self):
        results = [
            {"name": "A", "place_id": "1", "address": "", "city": "", "website": "", "phone": "", "google_data": {}},
            {"name": "B", "place_id": "2", "address": "", "city": "", "website": "", "phone": "", "google_data": {}},
        ]
        with patch("gcrm.tools.search.google_maps_search", return_value=results):
            place = signs.resolve_business("A")
        assert place["place_id"] == "1"


class TestBuildContactFields:
    def test_uses_place_when_accepted(self):
        fields = signs.build_contact_fields(
            "Bäckerei Roth",
            {"business_type": "bakery", "tagline": "Frisch seit 1980"},
            {"name": "Bäckerei Roth", "city": "Augsburg", "website": "https://roth.de",
             "phone": "+49 821 1", "address": "Hauptstr 1"},
        )
        assert fields["company"] == "Bäckerei Roth"
        assert fields["city"] == "Augsburg"
        assert fields["website"] == "https://roth.de"
        assert fields["industry"] == "bakery"
        assert fields["note"] == "Frisch seit 1980"

    def test_falls_back_to_sign_fields_when_no_place(self):
        fields = signs.build_contact_fields(
            "Bäckerei Roth", {"phone": "+49 821 1", "website": "https://roth.de"}, None,
        )
        assert fields["company"] == "Bäckerei Roth"
        assert fields["phone"] == "+49 821 1"
        assert "city" not in fields


class TestPromotePeople:
    def test_saves_each_named_person(self):
        with patch("gcrm.tools.db.save_person", side_effect=[10, 11]) as msave:
            ids = signs.promote_people(5, [
                {"name": "Anna Roth", "role": "Owner", "email": "anna@roth.de"},
                {"name": "Ben Roth", "role": "Manager"},
            ])
        assert ids == [10, 11]
        assert msave.call_args_list[0].kwargs["source"] == "sign_research"
        assert msave.call_args_list[0].kwargs["contact_id"] == 5

    def test_skips_unnamed_entries(self):
        with patch("gcrm.tools.db.save_person") as msave:
            ids = signs.promote_people(5, [{"role": "Owner"}])
        assert ids == []
        msave.assert_not_called()

    def test_one_failure_does_not_drop_the_rest(self):
        with patch("gcrm.tools.db.save_person", side_effect=[RuntimeError("db down"), 11]):
            ids = signs.promote_people(5, [{"name": "Bad"}, {"name": "Good"}])
        assert ids == [11]


class TestFindKeyPeople:
    def test_no_name_returns_empty(self):
        assert signs.find_key_people({}) == []

    def test_search_failure_returns_empty(self):
        with patch("gcrm.tools.web_search", side_effect=RuntimeError("boom")):
            assert signs.find_key_people({"name": "Roth", "city": "Augsburg"}) == []

    def test_parses_array_response_and_skips_directory_domains(self):
        search_results = [
            {"title": "Home", "url": "https://roth.de", "snippet": ""},
            {"title": "Maps", "url": "https://google.com/maps/x", "snippet": ""},
        ]
        resp = MagicMock()
        resp.content = '[{"name": "Anna Roth", "role": "Owner", "email": "anna@roth.de", "phone": null}]'
        fake_llm = MagicMock()
        fake_llm.invoke.return_value = resp
        with patch("gcrm.tools.web_search", return_value=search_results), \
             patch("gcrm.tools.fetch_page", return_value="Kontakt: Anna Roth") as mfetch, \
             patch("gcrm.tools.llm.get_llm", return_value=fake_llm):
            people = signs.find_key_people({"name": "Bäckerei Roth", "city": "Augsburg", "country": "DE"})
        assert people == [{"name": "Anna Roth", "role": "Owner", "email": "anna@roth.de", "phone": None}]
        mfetch.assert_called_once_with("https://roth.de")  # directory domain skipped


class TestCaptureEndpoint:
    def test_requires_auth(self):
        assert client.post("/api/signs/1/discard").status_code in (401, 403)

    def test_happy_path_with_place_resolved(self):
        conn, cur = make_mock_conn()
        cur.fetchone.return_value = {"id": 5}
        fields = {"is_sign": True, "confidence": 80, "business_name": "Bäckerei Roth"}
        place = {"name": "Bäckerei Roth", "place_id": "abc", "address": "Hauptstr 1",
                 "city": "Augsburg", "website": "https://roth.de", "phone": "+49 821 1"}
        with patch("gcrm.api.routers.api_signs.db") as mock_db, \
             patch("gcrm.tools.cards.save_card_image", return_value="5.jpg"), \
             patch("gcrm.tools.signs.extract_sign_fields",
                   return_value={"fields": fields, "model": "claude-haiku-4-5-20251001", "cost_usd": 0.001}), \
             patch("gcrm.tools.signs.resolve_business", return_value=place), \
             patch("gcrm.tools.cards.find_possible_duplicate", return_value=None):
            mock_db.return_value.__enter__.return_value = conn
            r = client.post(
                "/api/signs", headers=AUTH,
                files={"image": ("sign.jpg", b"\xff\xd8\xff", "image/jpeg")},
                data={"gps_lat": "48.37", "gps_lng": "10.90"},
            )
        assert r.status_code == 200
        body = r.json()
        assert body["capture_id"] == 5
        assert body["is_sign"] is True
        assert body["place"]["place_id"] == "abc"


class TestConfirmEndpoint:
    def test_not_found(self):
        conn, cur = make_mock_conn(rows=[])
        with patch("gcrm.api.routers.api_signs.db") as mock_db:
            mock_db.return_value.__enter__.return_value = conn
            r = client.post("/api/signs/999/confirm", headers=AUTH, json={"business_name": "X"})
        assert r.status_code == 404

    def test_confirm_promotes_and_schedules_research(self):
        cap_row = {"id": 5, "status": "pending_review", "image_path": "5.jpg",
                   "extracted": {"business_name": "Bäckerei Roth"}, "place_json": None}
        conn, cur = make_mock_conn(rows=[cap_row])
        with patch("gcrm.api.routers.api_signs.db") as mock_db, \
             patch("gcrm.tools.cards.promote_to_contact", return_value=42) as mpromote, \
             patch("gcrm.tools.cards.delete_card_image") as mdelete, \
             patch("gcrm.tools.signs.research_business") as mresearch:
            mock_db.return_value.__enter__.return_value = conn
            r = client.post(
                "/api/signs/5/confirm", headers=AUTH,
                json={"business_name": "Bäckerei Roth", "accept_place": False},
            )
        assert r.status_code == 200
        assert r.json() == {"contact_id": 42, "capture_id": 5}
        assert mpromote.call_args.kwargs["source"] == "sign_scan"
        mdelete.assert_called_once_with("5.jpg")  # CARD_IMAGE_RETENTION_DAYS defaults to 0 in tests
        mresearch.assert_called_once_with(42)

    def test_empty_business_name_rejected(self):
        cap_row = {"id": 5, "status": "pending_review", "image_path": None,
                   "extracted": {}, "place_json": None}
        conn, cur = make_mock_conn(rows=[cap_row])
        with patch("gcrm.api.routers.api_signs.db") as mock_db:
            mock_db.return_value.__enter__.return_value = conn
            r = client.post("/api/signs/5/confirm", headers=AUTH, json={"business_name": "   "})
        assert r.status_code == 400
