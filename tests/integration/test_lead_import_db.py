"""Importing a lead list against the real schema (2026-11-05): new companies and people are
created, existing ones are matched and only their blank fields filled, a dry run writes
nothing, and importing the same list again changes nothing."""
import pytest

from gcrm.db.connection import db
from gcrm.lead_list import parse_lead_list
from gcrm.tools.db_lead_import import import_lead_list
from gcrm.tools.map_pins import latest_import_ids, pin_queue

pytestmark = pytest.mark.integration

LIST = """| Pg | # | Business | Location | Address | Website | Contact | Role | LinkedIn | LinkedIn status | Notes |
|---|---|---|---|---|---|---|---|---|---|---|
| 7 | 1 | Karwendel-Werke Huber GmbH & Co. KG | Nordwest I / III | Karwendelstr. 6-16, 86807 Buchloe | karwendel.de | Erika Muster | Sprecher der Geschäftsführung (Impressum) | [profile](https://www.linkedin.com/in/erika-muster-3a71/) | not sent | Dairy. |
| 7 | 2 | Karwendel-Werke Huber GmbH & Co. KG | Nordwest I / III | Karwendelstr. 6-16, 86807 Buchloe | karwendel.de | Paul Platzhalter | Geschäftsführer | — | no profile found | Press names him. |
| 8 | 3 | PCG – Public Cloud Group | Science Park II | Lise-Meitner-Str. 3-1, 89081 Ulm | pcg.io | Kim Beispiel | Geschäftsführer (Impressum) | [candidate](https://www.linkedin.com/in/kim-beispiel/) | not sent | |
| 8 | 4 | Beispiel AG | Innovationspark | — | — | Anna Berg | CTO | [profile](https://www.linkedin.com/in/anna-berg/) | connected | |
"""


def workspace_id() -> int:
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM workspaces WHERE slug = 'default'")
        return cur.fetchone()["id"]


def query(sql: str, *params) -> list[dict]:
    with db() as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        return [dict(row) for row in cur.fetchall()]


@pytest.fixture(autouse=True)
def no_geocoding(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("an import must not geocode (Nominatim refuses bulk requests)")
    monkeypatch.setattr("gcrm.tools.db_organizations.geocode", refuse)
    monkeypatch.setattr("gcrm.tools.db_people.geocode", refuse)


def run(apply=True, town="Buchloe"):
    return import_lead_list(parse_lead_list(LIST), list_name="buchloe-office-parks", default_town=town, apply=apply)


def test_a_new_list_creates_companies_people_and_candidate_deals(clean_database):
    report = run()
    assert (report["companies_new"], report["companies_existing"], report["people_new"]) == (3, 0, 4)
    karwendel = query("SELECT * FROM contacts WHERE name = 'Karwendel-Werke Huber GmbH & Co. KG'")[0]
    assert (karwendel["city"], karwendel["address"], karwendel["website"], karwendel["neighborhood"], karwendel["source"]) == (
        "Buchloe", "Karwendelstr. 6-16, 86807 Buchloe", "https://karwendel.de", "Nordwest I / III", "lead_list")
    assert "buchloe-office-parks" in karwendel["notes"] and "Dairy." in karwendel["notes"]
    stages = query("SELECT d.pipeline_stage FROM deals d WHERE d.contact_id = %s", karwendel["id"])
    assert stages == [{"pipeline_stage": "candidate"}]
    people = query("SELECT name, title, linkedin_url, source FROM people WHERE contact_id = %s ORDER BY name", karwendel["id"])
    assert people == [
        {"name": "Erika Muster", "title": "Sprecher der Geschäftsführung (Impressum)",
         "linkedin_url": "https://www.linkedin.com/in/erika-muster-3a71/", "source": "lead_list"},
        {"name": "Paul Platzhalter", "title": "Geschäftsführer", "linkedin_url": None, "source": "lead_list"},
    ]


def test_a_candidate_profile_and_the_status_go_into_the_notes_and_connected_is_flagged(clean_database):
    run()
    tastan = query("SELECT linkedin_url, notes, is_linkedin_contact FROM people WHERE name = 'Kim Beispiel'")[0]
    assert tastan["linkedin_url"] is None and tastan["is_linkedin_contact"] is False
    assert "https://www.linkedin.com/in/kim-beispiel/" in tastan["notes"] and "not sent" in tastan["notes"]
    berg = query("SELECT is_linkedin_contact FROM people WHERE name = 'Anna Berg'")[0]
    assert berg["is_linkedin_contact"] is True


def test_a_company_without_a_town_in_its_address_gets_the_lists_town(clean_database):
    run(town="Buchloe")
    assert query("SELECT city FROM contacts WHERE name = 'Beispiel AG'") == [{"city": "Buchloe"}]


def test_a_dry_run_writes_nothing_but_reports_what_it_would_do(clean_database):
    report = run(apply=False)
    assert (report["companies_new"], report["people_new"]) == (3, 4)
    assert query("SELECT count(*) AS n FROM contacts") == [{"n": 0}]


def test_importing_the_same_list_again_changes_nothing(clean_database):
    run()
    report = run()
    assert (report["companies_new"], report["companies_existing"], report["people_new"]) == (0, 3, 0)
    assert query("SELECT count(*) AS n FROM contacts") == [{"n": 3}]
    assert query("SELECT count(*) AS n FROM people") == [{"n": 4}]


def test_an_existing_company_keeps_its_data_and_only_gets_blanks_filled(clean_database):
    with db() as conn:
        conn.cursor().execute(
            "INSERT INTO contacts (name, city, website, workspace_id, source) "
            "VALUES ('Karwendel-Werke Huber GmbH & Co. KG', 'Buchloe', 'https://www.karwendel.de/de', %s, 'card_capture')",
            (workspace_id(),))
    report = run()
    assert report["companies_existing"] == 1
    karwendel = query("SELECT website, address, source FROM contacts WHERE name = 'Karwendel-Werke Huber GmbH & Co. KG'")[0]
    assert karwendel == {"website": "https://www.karwendel.de/de", "address": "Karwendelstr. 6-16, 86807 Buchloe",
                         "source": "card_capture"}


def test_the_import_is_recorded_as_a_run_with_its_company_ids(clean_database):
    report = run()
    runs = query("SELECT output_json FROM agent_runs WHERE agent_name = 'lead_import'")
    assert sorted(runs[0]["output_json"]["company_ids"]) == sorted(report["company_ids"])


def test_the_latest_imports_companies_wait_to_be_pinned(clean_database):
    report = run()
    assert sorted(latest_import_ids()) == sorted(report["company_ids"])
    karwendel = query("SELECT id FROM contacts WHERE name = 'Karwendel-Werke Huber GmbH & Co. KG'")[0]["id"]
    assert karwendel in {row["id"] for row in pin_queue(workspace_id(), ids=latest_import_ids())}
