"""Who do I know at this organization? — against the real schema."""
import pytest

from gcrm.db.connection import db
from gcrm.tools.db_linkedin import get_known_people_for_org
from gcrm.tools.db_people import save_person

pytestmark = pytest.mark.integration


def _company(name: str) -> int:
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute(
            "INSERT INTO contacts (name, city, status, workspace_id) "
            "VALUES (%s, 'Augsburg', 'cold', (SELECT id FROM workspaces WHERE slug = 'default')) RETURNING id",
            (name,),
        )
        return cursor.fetchone()["id"]


def test_everyone_linked_is_listed_people_met_in_person_first(clean_database, monkeypatch):
    monkeypatch.setattr("gcrm.tools.db_people.geocode", lambda city, country: None)
    acme, other = _company("Acme GmbH"), _company("Other AG")
    linkedin = save_person("Anna LinkedIn", contact_id=acme, source="linkedin_import", allow_duplicate=True)
    by_hand = save_person("Bernd Hand", contact_id=acme, source="manual", pipeline_stage="prospect",
                          allow_duplicate=True)
    card = save_person("Zora Card", contact_id=acme, source="card_capture", email="zora@example.test",
                       met_at="Messe", allow_duplicate=True)
    gone = save_person("Gone Person", contact_id=acme, source="card_capture", allow_duplicate=True)
    save_person("Elsewhere Person", contact_id=other, source="card_capture", allow_duplicate=True)
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("UPDATE people SET is_linkedin_contact = TRUE, "
                       "linkedin_url = 'https://www.linkedin.com/in/anna' WHERE id = %s", (linkedin,))
        cursor.execute("UPDATE people SET deleted_at = NOW() WHERE id = %s", (gone,))

    linked = get_known_people_for_org(acme)["linked"]

    assert [p["id"] for p in linked] == [card, by_hand, linkedin]
    assert linked[0]["email"] == "zora@example.test" and linked[0]["met_at"] == "Messe"
    assert linked[1]["pipeline_stage"] == "prospect"
    assert linked[2]["is_linkedin_contact"] is True
