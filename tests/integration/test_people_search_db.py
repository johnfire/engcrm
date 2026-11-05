"""People found by web search against the real schema: only ready, unsearched companies are
picked; a found person lands on an existing LinkedIn connection instead of a duplicate; a
person with no public profile is recorded as searched; profiles already stored are kept."""
import pytest

from gcrm.db.connection import db
from gcrm.tools.db_people_search import (
    get_organizations_needing_people,
    mark_people_searched,
    save_found_person,
)

pytestmark = pytest.mark.integration


def add_company(name: str, status: str) -> dict:
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM workspaces WHERE slug = 'default'")
        workspace_id = cur.fetchone()["id"]
        cur.execute("INSERT INTO contacts (name, city, workspace_id) VALUES (%s, 'Untermeitingen', %s) RETURNING id",
                    (name, workspace_id))
        contact_id = cur.fetchone()["id"]
        cur.execute("INSERT INTO deals (workspace_id, offer_id, contact_id, pipeline_stage, status) "
                    "VALUES (%s, offer_id_for(%s, 'consulting'), %s, 'suspect', %s)",
                    (workspace_id, workspace_id, contact_id, status))
    return {"id": contact_id, "name": name, "city": "Untermeitingen", "country": "DE"}


def add_connection(company: dict, name: str, linkedin_url: str) -> int:
    with db() as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO people (name, contact_id, source, linkedin_url, is_linkedin_contact, workspace_id) "
                    "SELECT %s, %s, 'linkedin_import', %s, TRUE, id FROM workspaces WHERE slug = 'default' "
                    "RETURNING id", (name, company["id"], linkedin_url))
        return cur.fetchone()["id"]


@pytest.fixture(autouse=True)
def no_geocoding(monkeypatch):
    monkeypatch.setattr("gcrm.tools.db_people.geocode", lambda city, country: None)


def test_only_ready_companies_not_yet_searched_are_picked(clean_database):
    ready, other = add_company("Faist Systeme GmbH", "ready"), add_company("Meile GmbH", "none")
    assert [row["id"] for row in get_organizations_needing_people()] == [ready["id"]]
    mark_people_searched(ready["id"])
    assert get_organizations_needing_people() == []
    assert other["id"]


def test_a_person_found_by_profile_is_the_existing_connection(clean_database):
    company = add_company("Faist Systeme GmbH", "ready")
    person_id = add_connection(company, "Anwar Amir", "https://www.linkedin.com/in/anwar-amir-9/")
    saved = save_found_person(company, {"name": "Anwar Amir", "role": "Produktionsleiter",
                                        "linkedin_url": "https://de.linkedin.com/in/anwar-amir-9"})
    assert saved["person_id"] == person_id and saved["is_connection"] is True
    assert saved["linkedin_url"] == "https://www.linkedin.com/in/anwar-amir-9/"  # kept, not replaced


def test_a_person_with_no_public_profile_is_saved_and_marked_searched(clean_database):
    company = add_company("Meile GmbH", "ready")
    saved = save_found_person(company, {"name": "Klaus Meile", "role": "Geschäftsführer", "source_url": None})
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT contact_id, title, source, linkedin_url, xing_url, profile_searched_at, notes "
                    "FROM people WHERE id = %s", (saved["person_id"],))
        row = cur.fetchone()
    assert (row["contact_id"], row["title"], row["source"]) == (company["id"], "Geschäftsführer", "research_agent")
    assert row["linkedin_url"] is None and row["xing_url"] is None and row["profile_searched_at"] is not None
    assert row["notes"] == "Found via web search."


def test_saving_the_same_person_twice_does_not_duplicate_them(clean_database):
    company = add_company("Meile GmbH", "ready")
    first = save_found_person(company, {"name": "Klaus Meile", "role": "Geschäftsführer"})
    second = save_found_person(company, {"name": "Klaus Meile", "role": "Geschäftsführer",
                                         "xing_url": "https://www.xing.com/profile/Klaus_Meile"})
    assert first["person_id"] == second["person_id"]
    assert second["xing_url"] == "https://www.xing.com/profile/Klaus_Meile"


def test_a_gather_run_searches_its_own_companies_whether_judged_or_not(clean_database):
    """Plan 2026-11-05: the people finder runs in Gather, before the scout."""
    unjudged, other = add_company("Meile GmbH", "none"), add_company("Faist Systeme GmbH", "ready")
    assert [row["id"] for row in get_organizations_needing_people(ids=[unjudged["id"]])] == [unjudged["id"]]
    mark_people_searched(unjudged["id"])
    assert get_organizations_needing_people(ids=[unjudged["id"]]) == []
    assert other["id"]
