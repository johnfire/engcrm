"""The follow-up list orders dates before pagination in either direction."""
from datetime import date

import pytest

from gcrm.db.connection import db
from gcrm.tools.db_interactions import log_meeting_note
from gcrm.tools.db_organizations import save_organization
from gcrm.tools.deal_records import get_deals
from gcrm.tools.follow_up_queries import find_follow_ups
from gcrm.tools.follow_ups import create_follow_up

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("direction,expected", [
    ("asc", ["Earlier", "Later", "Undated"]),
    ("desc", ["Later", "Earlier", "Undated"]),
])
def test_date_order_and_undated_last_across_pages(clean_database, monkeypatch, direction, expected):
    monkeypatch.setattr("gcrm.tools.db_organizations.geocode", lambda city, country: None)
    organization = save_organization("Example GmbH", "Augsburg", source="test_fixture")
    deal = get_deals("organization", organization)[0]
    for text, due in [("Undated", None), ("Later", date(2027, 1, 5)), ("Earlier", date(2026, 12, 5))]:
        create_follow_up(deal_id=deal["id"], task_type="commitment", task_text=text, due_date=due)

    first_page = find_follow_ups(direction=direction, limit=2, offset=0)
    second_page = find_follow_ups(direction=direction, limit=2, offset=2)
    assert [task["task_text"] for task in first_page + second_page] == expected
    filtered = find_follow_ups(direction=direction, date_from=date(2027, 1, 1))
    assert {task["task_text"] for task in filtered} == {"Later", "Undated"}


def test_activity_offer_is_visible_even_when_no_deal_exists(clean_database, monkeypatch):
    monkeypatch.setattr("gcrm.tools.db_organizations.geocode", lambda city, country: None)
    organization = save_organization("Example GmbH", "Augsburg", source="test_fixture")
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM offers WHERE slug='training' AND workspace_id=(SELECT workspace_id FROM contacts WHERE id=%s)", (organization,))
        offer_id = cursor.fetchone()["id"]
    log_meeting_note(organization, "phone", "Spoke", follow_up_text="Send training outline",
                     follow_up_type="commitment", offer_id=offer_id)
    tasks = find_follow_ups(offer_id=offer_id)
    assert len(tasks) == 1
    assert (tasks[0]["offer_name"], tasks[0]["deal_id"], tasks[0]["pipeline_stage"]) == ("Training", None, None)


def test_soft_deleted_owner_is_hidden_until_restored(clean_database, monkeypatch):
    monkeypatch.setattr("gcrm.tools.db_organizations.geocode", lambda city, country: None)
    organization = save_organization("Example GmbH", "Augsburg", source="test_fixture")
    create_follow_up(contact_id=organization, task_type="commitment", task_text="Send details")
    with db() as connection:
        connection.cursor().execute("UPDATE contacts SET deleted_at=NOW() WHERE id=%s", (organization,))
    assert find_follow_ups() == []
    with db() as connection:
        connection.cursor().execute("UPDATE contacts SET deleted_at=NULL WHERE id=%s", (organization,))
    assert [task["task_text"] for task in find_follow_ups()] == ["Send details"]


def test_search_company_finds_a_linked_persons_follow_up(clean_database, monkeypatch):
    from gcrm.tools.db_people import save_person

    monkeypatch.setattr("gcrm.tools.db_organizations.geocode", lambda city, country: None)
    organization = save_organization("Example Engineering", "Augsburg", source="test_fixture")
    person = save_person("Anna Contact", contact_id=organization, source="test_fixture", geocode_city=False)
    create_follow_up(person_id=person, task_type="check_in", task_text="Call Anna")
    assert [task["task_text"] for task in find_follow_ups(search="Engineering")] == ["Call Anna"]
