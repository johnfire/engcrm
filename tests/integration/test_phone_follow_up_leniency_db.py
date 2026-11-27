"""The phone API stays lenient: older app builds cannot send a follow-up type, so a next step or
promise without one is saved for review and never refused. With a type it is active at once."""
import pytest
from fastapi.testclient import TestClient

from gcrm.api.jwt_auth import create_token
from gcrm.api.main import app
from gcrm.db.connection import db
from gcrm.tools.db_organizations import save_organization
from gcrm.tools.db_people import save_person
from gcrm.tools.deal_records import get_deals

pytestmark = pytest.mark.integration

PHONE = {"Authorization": f"Bearer {create_token('admin')}"}


@pytest.mark.parametrize("chosen, expected", [(None, ("review", None)), ("check_in", ("active", "check_in"))])
def test_every_phone_write_is_accepted_with_or_without_a_type(clean_database, monkeypatch, chosen, expected):
    monkeypatch.setattr("gcrm.tools.db_organizations.geocode", lambda city, country: None)
    organization = save_organization("Beispiel Werke GmbH", "Friedrichshafen", source="test_fixture")
    person = save_person("Ada Beispiel", source="test_fixture")
    deal = get_deals("organization", organization)[0]
    next_step = {"task_type": chosen} if chosen else {}
    promise = {"follow_up_type": chosen} if chosen else {}
    client = TestClient(app)
    responses = [
        client.put(f"/api/deals/{deal['id']}/next-step", headers=PHONE,
                   json={"next_step": "Deal step", "next_step_date": None, **next_step}),
        client.put(f"/api/people/{person}/next-step", headers=PHONE,
                   json={"next_step": "Person step", "next_step_date": None, **next_step}),
        client.post(f"/api/contacts/{organization}/notes", headers=PHONE,
                    json={"note": "Spoke", "follow_up_text": "Note promise", "offer": "general", **promise}),
        client.post("/api/voice/confirm", headers=PHONE,
                    json={"contact_id": organization, "summary": "Memo", "follow_up_text": "Voice promise", **promise}),
    ]
    assert [response.status_code for response in responses] == [200, 200, 200, 200]
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT task_text, status, task_type FROM follow_ups")
        saved = {row["task_text"]: (row["status"], row["task_type"]) for row in cursor.fetchall()}
    assert saved == dict.fromkeys(["Deal step", "Person step", "Note promise", "Voice promise"], expected)
