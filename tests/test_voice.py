"""Voice memo: transcript structuring, the /api/voice endpoints, date validation.
The LLM, transcription, and DB are all mocked."""
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

import gcrm.api.main as main
from gcrm.api.jwt_auth import create_token
from gcrm.api.routers import api_voice
from gcrm.json_parsing import parse_llm_json
from gcrm.tools import voice

client = TestClient(main.app)
AUTH = {"Authorization": f"Bearer {create_token('admin')}"}


def _llm_returning(content: str):
    resp = MagicMock()
    resp.content = content
    llm = MagicMock()
    llm.invoke.return_value = resp
    return llm


class TestParsing:
    def test_parse_json_fenced(self):
        assert parse_llm_json('```json\n{"summary":"hi"}\n```') == {"summary": "hi"}

    def test_parse_json_prose_wrapped(self):
        assert parse_llm_json('Sure: {"summary":"x"} done') == {"summary": "x"}

    def test_valid_iso_date(self):
        assert api_voice._valid_iso_date("2026-07-15") == "2026-07-15"
        assert api_voice._valid_iso_date("next friday") is None
        assert api_voice._valid_iso_date("") is None
        assert api_voice._valid_iso_date(None) is None


class TestStructure:
    def test_parses_llm_json(self):
        llm = _llm_returning(
            '{"summary":"Met Anna","contact_query":"Acme","follow_up_date":"2026-07-01",'
            '"follow_up_text":"call","is_new_lead":false}'
        )
        with patch("gcrm.tools.llm.get_llm", return_value=llm):
            out = voice.structure_transcript("Met Anna at Acme...", "2026-06-23")
        assert out["contact_query"] == "Acme"
        assert out["follow_up_date"] == "2026-07-01"
        assert out["is_new_lead"] is False

    def test_fallback_on_bad_json(self):
        with patch("gcrm.tools.llm.get_llm", return_value=_llm_returning("not json at all")):
            out = voice.structure_transcript("hello world", "2026-06-23")
        assert out["summary"] == "hello world"
        assert out["is_new_lead"] is False


class TestVoiceEndpoints:
    def test_requires_auth(self):
        assert client.post("/api/voice").status_code in (401, 403)

    def test_process_happy_path(self):
        with patch("gcrm.api.routers.api_voice.transcribe",
                   return_value="Met Anna at Acme, follow up in two weeks"), \
             patch("gcrm.api.routers.api_voice.structure_transcript", return_value={
                 "summary": "Met Anna at Acme", "contact_query": "Acme",
                 "follow_up_date": "2026-07-07", "follow_up_text": "follow up", "is_new_lead": False}), \
             patch("gcrm.api.routers.api_voice.search_organizations_by_name",
                   return_value=[{"id": 9, "name": "Acme", "city": "Augsburg",
                                  "email": None, "phone": None, "decision_maker": None}]):
            r = client.post("/api/voice", headers=AUTH,
                            files={"audio": ("memo.m4a", b"\x00\x01\x02", "audio/m4a")})
        assert r.status_code == 200
        body = r.json()
        assert body["summary"] == "Met Anna at Acme"
        assert body["follow_up_date"] == "2026-07-07"
        assert body["candidates"][0]["id"] == 9

    def test_confirm_existing_organization_passes_followup(self):
        with patch("gcrm.api.routers.api_voice.log_voice_interaction") as mlog:
            r = client.post("/api/voice/confirm", headers=AUTH, json={
                "contact_id": 9, "summary": "Met Anna",
                "follow_up_date": "2026-07-07", "follow_up_text": "call"})
        assert r.status_code == 200
        assert r.json()["contact_id"] == 9
        assert mlog.call_args.kwargs["next_action_date"] == "2026-07-07"

    def test_confirm_new_organization_creates(self):
        with patch("gcrm.api.routers.api_voice.save_organization", return_value=42) as msave, \
             patch("gcrm.api.routers.api_voice.log_voice_interaction"):
            r = client.post("/api/voice/confirm", headers=AUTH,
                            json={"new_organization_name": "New Co", "summary": "cold intro"})
        assert r.status_code == 200
        assert r.json()["contact_id"] == 42
        assert msave.called

    def test_confirm_drops_invalid_date(self):
        with patch("gcrm.api.routers.api_voice.log_voice_interaction") as mlog:
            r = client.post("/api/voice/confirm", headers=AUTH,
                            json={"contact_id": 9, "summary": "x", "follow_up_date": "garbage"})
        assert r.status_code == 200
        assert mlog.call_args.kwargs["next_action_date"] is None
