"""Filling a person's blank city from their company, against the real schema."""
import pytest

from gcrm.db.connection import db
from gcrm.tools.db_people import save_person
from gcrm.tools.people_city import fill_blank_cities, survey

pytestmark = pytest.mark.integration


def _company(name: str, city: str | None, country: str | None = "DE") -> int:
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute(
            "INSERT INTO contacts (name, city, country, workspace_id) "
            "VALUES (%s, %s, %s, (SELECT id FROM workspaces WHERE slug = 'default')) RETURNING id",
            (name, city, country),
        )
        return cursor.fetchone()["id"]


def _city(person_id: int) -> tuple:
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT city, country FROM people WHERE id = %s", (person_id,))
        row = cursor.fetchone()
        return row["city"], row["country"]


def test_blank_cities_are_filled_and_differing_ones_left_alone(clean_database, monkeypatch):
    monkeypatch.setattr("gcrm.tools.db_people.geocode", lambda city, country: None)
    _people_trigger("DISABLE")  # recreate the blanks that existed before migration 058
    try:
        _check_survey_and_fill()
    finally:
        _people_trigger("ENABLE")


def _people_trigger(state: str) -> None:
    with db() as connection:
        connection.cursor().execute(f"ALTER TABLE people {state} TRIGGER people_city_from_company")


def _check_survey_and_fill():
    vienna = _company("Wiener Firma", "Wien", "AT")
    augsburg = _company("Augsburger Firma", "Augsburg")
    nowhere = _company("Ortlose Firma", None)
    blank = save_person("Blank Person", contact_id=vienna, allow_duplicate=True, source="test_fixture")
    branch = save_person("Branch Person", city="Friedberg", contact_id=augsburg, allow_duplicate=True, source="test_fixture")
    same = save_person("Same Person", city="86150 Augsburg", contact_id=augsburg, allow_duplicate=True, source="test_fixture")
    stuck = save_person("Stuck Person", contact_id=nowhere, allow_duplicate=True, source="test_fixture")
    save_person("Loose Person", allow_duplicate=True, source="test_fixture")

    report = survey()

    assert [r["id"] for r in report["fill"]] == [blank]
    assert [r["id"] for r in report["mismatch"]] == [branch]
    assert [r["id"] for r in report["company_has_no_city"]] == [stuck]
    assert report["same"] == 1 and report["unlinked_without_city"] == 1

    assert fill_blank_cities([r["id"] for r in report["fill"]] + [branch, same]) == 1
    assert _city(blank) == ("Wien", "AT")
    assert _city(branch)[0] == "Friedberg"
    assert _city(same)[0] == "86150 Augsburg"
    assert survey()["fill"] == []


def test_a_new_person_takes_the_company_city(clean_database, monkeypatch):
    monkeypatch.setattr("gcrm.tools.db_people.geocode", lambda city, country: None)
    vienna = _company("Wiener Firma", "Wien", "AT")

    created = save_person("New Person", contact_id=vienna, allow_duplicate=True, source="test_fixture")
    with_city = save_person("Card Person", city="Graz", contact_id=vienna, allow_duplicate=True, source="test_fixture")

    assert _city(created) == ("Wien", "AT")
    assert _city(with_city)[0] == "Graz"


def test_linking_a_person_later_fills_a_blank_city(clean_database):
    augsburg = _company("Augsburger Firma", "Augsburg")
    deleted = _company("Geloeschte Firma", "Ulm")
    person = save_person("Loose Person", allow_duplicate=True, source="test_fixture")
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("UPDATE contacts SET deleted_at = NOW() WHERE id = %s", (deleted,))
        cursor.execute("UPDATE people SET contact_id = %s WHERE id = %s", (deleted, person))
    assert _city(person)[0] is None

    with db() as connection:
        connection.cursor().execute("UPDATE people SET contact_id = %s WHERE id = %s", (augsburg, person))
    assert _city(person) == ("Augsburg", "DE")


def test_a_company_getting_its_city_passes_it_to_people_without_one(clean_database, monkeypatch):
    monkeypatch.setattr("gcrm.tools.db_people.geocode", lambda city, country: None)
    company = _company("Neue Firma", None, None)
    blank = save_person("Blank Person", contact_id=company, allow_duplicate=True, source="test_fixture")
    elsewhere = save_person("Elsewhere Person", city="Friedberg", contact_id=company, allow_duplicate=True, source="test_fixture")

    with db() as connection:
        connection.cursor().execute("UPDATE contacts SET city = 'Augsburg', country = 'DE' WHERE id = %s",
                                    (company,))

    assert _city(blank) == ("Augsburg", "DE")
    assert _city(elsewhere)[0] == "Friedberg"
