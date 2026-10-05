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
            "INSERT INTO contacts (name, city, country, status, workspace_id) "
            "VALUES (%s, %s, %s, 'cold', (SELECT id FROM workspaces WHERE slug = 'default')) RETURNING id",
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
    vienna = _company("Wiener Firma", "Wien", "AT")
    augsburg = _company("Augsburger Firma", "Augsburg")
    nowhere = _company("Ortlose Firma", None)
    blank = save_person("Blank Person", contact_id=vienna, allow_duplicate=True)
    branch = save_person("Branch Person", city="Friedberg", contact_id=augsburg, allow_duplicate=True)
    same = save_person("Same Person", city="86150 Augsburg", contact_id=augsburg, allow_duplicate=True)
    stuck = save_person("Stuck Person", contact_id=nowhere, allow_duplicate=True)
    save_person("Loose Person", allow_duplicate=True)

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
