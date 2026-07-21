"""Business-card capture: extraction parsing, dedup, promotion mapping, and the
capture endpoint. DB and the vision LLM are mocked — these run without Postgres
or a live Anthropic key."""
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

import gcrm.api.main as main
from gcrm.api.jwt_auth import create_token
from gcrm.json_parsing import parse_llm_json
from gcrm.tools import cards

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


class TestParsing:
    def test_plain_json(self):
        assert parse_llm_json('{"a": 1}') == {"a": 1}

    def test_markdown_fenced(self):
        assert parse_llm_json('```json\n{"a": 2}\n```') == {"a": 2}

    def test_prose_wrapped(self):
        assert parse_llm_json('Here you go: {"a": 3} — done') == {"a": 3}

    def test_content_to_text_str_and_blocks(self):
        assert cards._content_to_text("hi") == "hi"
        assert cards._content_to_text([{"text": "a"}, {"text": "b"}]) == "ab"

    def test_country_code_normalizes(self):
        assert cards._country_code("DE") == "DE"
        assert cards._country_code("at") == "AT"
        assert cards._country_code("Germany") == "DE"   # non-ISO → default
        assert cards._country_code("") == "DE"
        assert cards._country_code(None) == "DE"


class TestExtraction:
    def test_extract_parses_and_costs(self):
        resp = MagicMock()
        resp.content = '{"is_card": true, "confidence": 90, "company": "ACME", "name": "Anna Roth"}'
        resp.usage_metadata = {"input_tokens": 1500, "output_tokens": 200}
        fake_llm = MagicMock()
        fake_llm.invoke.return_value = resp
        with patch("gcrm.tools.llm.get_llm", return_value=fake_llm):
            out = cards.extract_card_fields(b"\xff\xd8\xff-fake-jpeg")
        assert out["fields"]["company"] == "ACME"
        assert out["model"] == "claude-haiku-4-5-20251001"
        # (1500*0.80 + 200*4.00) / 1e6 = 0.002
        assert abs(out["cost_usd"] - 0.002) < 1e-6

    def test_extract_handles_failure(self):
        fake_llm = MagicMock()
        fake_llm.invoke.side_effect = RuntimeError("boom")
        with patch("gcrm.tools.llm.get_llm", return_value=fake_llm):
            out = cards.extract_card_fields(b"x")
        assert out["fields"]["is_card"] is False
        assert "boom" in out["fields"]["error"]
        assert out["cost_usd"] == 0.0


class TestDedup:
    def test_email_match(self):
        conn, _ = make_mock_conn(rows=[{"id": 7, "name": "ACME", "city": "Augsburg",
                                        "email": "anna@acme.de", "phone": None}])
        with patch("gcrm.db.connection.db") as mock_db:
            mock_db.return_value.__enter__.return_value = conn
            dup = cards.find_possible_duplicate({"email": "anna@acme.de"})
        assert dup["id"] == 7

    def test_no_match_returns_none(self):
        conn, _ = make_mock_conn(rows=[])
        with patch("gcrm.db.connection.db") as mock_db:
            mock_db.return_value.__enter__.return_value = conn
            dup = cards.find_possible_duplicate(
                {"email": "x@nowhere.de", "company": "Z", "city": "C", "phone": "+49 821 999"}
            )
        assert dup is None


class TestPromote:
    def test_maps_company_and_decision_maker(self):
        conn, cur = make_mock_conn()
        with patch("gcrm.tools.db.save_contact", return_value=42) as msave, \
             patch("gcrm.db.connection.db") as mock_db:
            mock_db.return_value.__enter__.return_value = conn
            cid = cards.promote_to_contact({
                "company": "ACME GmbH", "name": "Anna Roth", "title": "CTO",
                "email": "anna@acme.de", "city": "Augsburg", "country": "DE",
                "address": "Hauptstr 1", "industry": "Software",
            })
        assert cid == 42
        assert msave.call_args.kwargs["name"] == "ACME GmbH"   # company → name
        assert msave.call_args.kwargs["email"] == "anna@acme.de"
        upd_sql, upd_params = cur.execute.call_args_list[-1].args
        assert "decision_maker" in upd_sql and "source=%s" in upd_sql
        assert upd_params[0] == "Anna Roth, CTO"               # person+title → decision_maker
        assert upd_params[2] == "card_capture"                 # default source unchanged

    def test_source_param_overrides_default(self):
        conn, cur = make_mock_conn()
        with patch("gcrm.tools.db.save_contact", return_value=9), \
             patch("gcrm.db.connection.db") as mock_db:
            mock_db.return_value.__enter__.return_value = conn
            cid = cards.promote_to_contact({"company": "Sign Co", "city": "Munich"}, source="sign_scan")
        assert cid == 9
        upd_params = cur.execute.call_args_list[-1].args[1]
        assert upd_params[2] == "sign_scan"

    def test_falls_back_to_person_name(self):
        conn, cur = make_mock_conn()
        with patch("gcrm.tools.db.save_contact", return_value=1) as msave, \
             patch("gcrm.db.connection.db") as mock_db:
            mock_db.return_value.__enter__.return_value = conn
            cards.promote_to_contact({"name": "Freelancer Bob", "city": "Munich"})
        assert msave.call_args.kwargs["name"] == "Freelancer Bob"

    def test_duplicate_returns_zero(self):
        conn, _ = make_mock_conn()
        with patch("gcrm.tools.db.save_contact", return_value=0), \
             patch("gcrm.db.connection.db") as mock_db:
            mock_db.return_value.__enter__.return_value = conn
            assert cards.promote_to_contact({"company": "Dup"}) == 0


class TestCaptureEndpoint:
    def test_requires_auth(self):
        assert client.get("/api/cards").status_code in (401, 403)

    def test_happy_path(self):
        conn, cur = make_mock_conn()
        cur.fetchone.return_value = {"id": 5}  # INSERT ... RETURNING id
        fields = {"is_card": True, "confidence": 88, "company": "ACME", "email": "a@acme.de"}
        with patch("gcrm.api.routers.api_cards.db") as mock_db, \
             patch("gcrm.tools.cards.save_card_image", return_value="5.jpg"), \
             patch("gcrm.tools.cards.extract_card_fields",
                   return_value={"fields": fields, "model": "claude-haiku-4-5-20251001", "cost_usd": 0.002}), \
             patch("gcrm.tools.cards.find_possible_duplicate", return_value=None):
            mock_db.return_value.__enter__.return_value = conn
            r = client.post("/api/cards", headers=AUTH,
                            files={"image": ("card.jpg", b"\xff\xd8\xff", "image/jpeg")})
        assert r.status_code == 200
        body = r.json()
        assert body["capture_id"] == 5
        assert body["is_card"] is True
        assert body["fields"]["company"] == "ACME"
