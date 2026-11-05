"""Transactional company/person entry against PostgreSQL, including retries and isolation."""
from concurrent.futures import ThreadPoolExecutor

import pytest

from gcrm.db.connection import db
from gcrm.tools.db_people import save_person
from gcrm.tools.web_person_capture import (
    ExistingPerson,
    capture_choices,
    link_existing_person,
    save_company_person,
)
from gcrm.workspace_context import require_workspace_scope, set_workspace_id

pytestmark = pytest.mark.integration


@pytest.fixture
def company(clean_database, monkeypatch):
    monkeypatch.setattr("gcrm.tools.db_people.geocode", lambda *args: None)
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("INSERT INTO contacts (name, city, country, workspace_id) "
                       "VALUES ('Trust in Soda', 'Lucerne', 'CH', "
                       "(SELECT id FROM workspaces WHERE slug='default')) RETURNING id, workspace_id")
        return dict(cursor.fetchone())


def capture(company_id, **overrides):
    arguments = {"fields": {"name": "Bruno Healy"}, "contact_id": company_id, "stage": "",
                 "offer": "consulting", "allow_duplicate": False, "spoke_today": False}
    return save_company_person(**{**arguments, **overrides})


def test_details_only_does_not_invent_a_conversation_or_deal(company):
    person_id = capture(company["id"])
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT contact_id, city, country, source FROM people WHERE id=%s", (person_id,))
        assert dict(cursor.fetchone()) == {"contact_id": company["id"], "city": "Lucerne",
                                          "country": "CH", "source": "manual_web"}
        cursor.execute("SELECT count(*) AS total FROM people_interactions WHERE person_id=%s", (person_id,))
        assert cursor.fetchone()["total"] == 0
        cursor.execute("SELECT count(*) AS total FROM deals WHERE person_id=%s", (person_id,))
        assert cursor.fetchone()["total"] == 0


def test_conversation_failure_rolls_back_the_new_person(company, monkeypatch):
    def unavailable_note(*args):
        raise RuntimeError("simulated failed note write")
    monkeypatch.setattr("gcrm.tools.web_person_capture.insert_person_note", unavailable_note)
    with pytest.raises(RuntimeError, match="failed note write"):
        capture(company["id"], spoke_today=True)
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT count(*) AS total FROM people")
        assert cursor.fetchone()["total"] == 0


def test_concurrent_repeated_saves_create_one_person_and_one_conversation(company):
    def attempt():
        try:
            return capture(company["id"], spoke_today=True)
        except ExistingPerson:
            return None
    with ThreadPoolExecutor(max_workers=2) as writers:
        saved_ids = list(writers.map(lambda _: attempt(), range(2)))
    assert sum(person_id is not None for person_id in saved_ids) == 1
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT count(*) AS total FROM people WHERE contact_id=%s", (company["id"],))
        assert cursor.fetchone()["total"] == 1
        cursor.execute("SELECT count(*) AS total FROM people_interactions")
        assert cursor.fetchone()["total"] == 1


def test_existing_person_at_another_company_is_never_moved(company):
    person_id = capture(company["id"])
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("INSERT INTO contacts (name, workspace_id) VALUES ('Other firm', %s) RETURNING id",
                       (company["workspace_id"],))
        other_id = cursor.fetchone()["id"]
    assert capture_choices(other_id, "Bruno")["person_matches"] == []
    with pytest.raises(ValueError, match="unlinked person"):
        link_existing_person(person_id, other_id, True)
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT contact_id FROM people WHERE id=%s", (person_id,))
        assert cursor.fetchone()["contact_id"] == company["id"]


def test_choices_and_writes_cannot_cross_workspace_boundaries(company):
    person_id = save_person("Bruno Healy", source="test_fixture")
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("INSERT INTO workspaces (name, slug) VALUES ('Other workspace', 'contact-other') "
                       "ON CONFLICT (slug) DO UPDATE SET name=EXCLUDED.name RETURNING id")
        other_workspace = cursor.fetchone()["id"]
    set_workspace_id(other_workspace)
    require_workspace_scope()
    try:
        assert capture_choices(company["id"], "Bruno")["organization"] is None
        with pytest.raises(ValueError, match="Organization not found"):
            link_existing_person(person_id, company["id"], True)
        with pytest.raises(ValueError, match="Organization not found"):
            capture(company["id"])
    finally:
        set_workspace_id(None)
        require_workspace_scope(False)


def test_deleted_people_and_companies_are_not_selectable(company):
    person_id = save_person("Bruno Healy", source="test_fixture")
    with db() as connection:
        connection.cursor().execute("UPDATE people SET deleted_at=NOW() WHERE id=%s", (person_id,))
    assert capture_choices(company["id"], "Bruno")["person_matches"] == []
    with pytest.raises(ValueError, match="unlinked person"):
        link_existing_person(person_id, company["id"], False)
    with db() as connection:
        connection.cursor().execute("UPDATE contacts SET deleted_at=NOW() WHERE id=%s", (company["id"],))
    with pytest.raises(ValueError, match="Organization not found"):
        capture(company["id"])
