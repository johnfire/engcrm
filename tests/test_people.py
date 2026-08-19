"""People: save_person dedup, card->person promotion mapping, and the mobile
/api/people endpoints. DB is mocked — runs without Postgres."""
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

import gcrm.api.main as main
from gcrm.api.jwt_auth import create_token
from gcrm.tools import cards, db_people

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


class TestSavePerson:
    def test_inserts_when_new(self):
        conn, cur = make_mock_conn()
        # email-dedup miss, name-dedup miss, then INSERT ... RETURNING id
        cur.fetchone.side_effect = [None, None, {"id": 11}]
        with patch("gcrm.tools.db_people.db") as mock_db:
            mock_db.return_value.__enter__.return_value = conn
            person_id = db_people.save_person(name="Anna Roth", email="anna@acme.de", contact_id=42)
        assert person_id == 11
        assert "INSERT INTO people" in cur.execute.call_args_list[-1].args[0]

    def test_stores_met_at(self):
        conn, cur = make_mock_conn()
        # no email, so only the name-dedup miss then INSERT ... RETURNING id
        cur.fetchone.side_effect = [None, {"id": 12}]
        with patch("gcrm.tools.db_people.db") as mock_db:
            mock_db.return_value.__enter__.return_value = conn
            db_people.save_person(name="Anna Roth", met_at="Kunstmesse Augsburg")
        insert = cur.execute.call_args_list[-1]
        assert "met_at" in insert.args[0]
        assert "Kunstmesse Augsburg" in insert.args[1]

    def test_dedups_on_email(self):
        conn, cur = make_mock_conn()
        cur.fetchone.side_effect = [{"id": 7}]  # email match on first lookup
        with patch("gcrm.tools.db_people.db") as mock_db:
            mock_db.return_value.__enter__.return_value = conn
            person_id = db_people.save_person(name="Anna", email="anna@acme.de")
        assert person_id == 7
        assert all(
            "INSERT" not in (call.args[0] if call.args else "")
            for call in cur.execute.call_args_list
        )


class TestMetAtOnRescan:
    """A re-scan deduping onto an existing person must still record the new
    place — but an empty field must never wipe the place already stored."""

    def test_updates_met_at_on_dedup_hit(self):
        conn, cur = make_mock_conn()
        cur.fetchone.side_effect = [{"id": 7}]  # email match
        with patch("gcrm.tools.db_people.db") as mock_db:
            mock_db.return_value.__enter__.return_value = conn
            person_id = db_people.save_person(
                name="Anna", email="anna@acme.de", met_at="Gallery opening",
            )
        assert person_id == 7
        update = cur.execute.call_args_list[-1]
        assert "UPDATE people SET met_at" in update.args[0]
        assert update.args[1] == ("Gallery opening", 7)

    def test_empty_met_at_does_not_clear(self):
        conn, cur = make_mock_conn()
        cur.fetchone.side_effect = [{"id": 7}]
        with patch("gcrm.tools.db_people.db") as mock_db:
            mock_db.return_value.__enter__.return_value = conn
            person_id = db_people.save_person(name="Anna", email="anna@acme.de")
        assert person_id == 7
        assert all(
            "UPDATE" not in (call.args[0] if call.args else "")
            for call in cur.execute.call_args_list
        )


class TestPromoteToPerson:
    def test_maps_card_fields(self):
        with patch("gcrm.tools.db.save_person", return_value=11) as msave:
            person_id = cards.promote_to_person(
                {"name": "Anna Roth", "title": "CTO", "email": "anna@acme.de",
                 "phone": "+49 821 1", "city": "Augsburg", "country": "DE",
                 "met_at": " Kunstmesse Augsburg "},
                contact_id=42,
            )
        assert person_id == 11
        assert msave.call_args.kwargs["name"] == "Anna Roth"
        assert msave.call_args.kwargs["title"] == "CTO"
        assert msave.call_args.kwargs["met_at"] == "Kunstmesse Augsburg"
        assert msave.call_args.kwargs["contact_id"] == 42
        assert msave.call_args.kwargs["source"] == "card_capture"

    def test_no_name_skips(self):
        with patch("gcrm.tools.db.save_person") as msave:
            assert cards.promote_to_person({"company": "ACME"}, contact_id=1) == 0
        msave.assert_not_called()


class TestPeopleEndpoint:
    def test_requires_auth(self):
        assert client.get("/api/people").status_code in (401, 403)

    def test_list(self):
        with patch("gcrm.api.routers.api_people.get_people",
                   return_value=[{"id": 1, "name": "Anna", "company": "ACME"}]):
            resp = client.get("/api/people", headers=AUTH)
        assert resp.status_code == 200
        assert resp.json()[0]["name"] == "Anna"

    def test_detail_404(self):
        with patch("gcrm.api.routers.api_people.get_person", return_value=None):
            resp = client.get("/api/people/999", headers=AUTH)
        assert resp.status_code == 404
