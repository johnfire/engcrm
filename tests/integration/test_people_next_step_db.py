"""A person's next step against the real schema: the field holds the current
plan, the note log keeps every change."""
from datetime import date

import pytest

from gcrm.db.connection import db
from gcrm.tools.db_people import save_person
from gcrm.tools.people_next_step import set_person_next_step

pytestmark = pytest.mark.integration


def _state(person_id: int) -> tuple:
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT next_step, next_step_date FROM people WHERE id = %s", (person_id,))
        row = cursor.fetchone()
        cursor.execute("SELECT method, note FROM people_interactions WHERE person_id = %s ORDER BY id",
                       (person_id,))
        return (row["next_step"], row["next_step_date"]), [(r["method"], r["note"]) for r in cursor.fetchall()]


def test_each_change_is_logged_and_a_repeat_save_is_not(clean_database):
    person = save_person("Anna Huber", allow_duplicate=True)

    set_person_next_step(person, "Invite to coffee", date(2026, 10, 15))
    assert set_person_next_step(person, " Invite to coffee ", date(2026, 10, 15))["logged"] is False
    set_person_next_step(person, "Send portfolio", None)
    set_person_next_step(person, "", None)

    field, log = _state(person)
    assert field == (None, None)
    assert log == [("next_step", "Invite to coffee (2026-10-15)"), ("next_step", "Send portfolio"),
                   ("next_step_done", "✓ Send portfolio")]


def test_the_field_holds_the_current_step(clean_database):
    person = save_person("Bernd Klein", allow_duplicate=True)

    set_person_next_step(person, "Call after the fair", date(2026, 11, 2))

    assert _state(person)[0] == ("Call after the fair", date(2026, 11, 2))


def test_clearing_an_empty_step_logs_nothing_and_unknown_people_are_none(clean_database):
    person = save_person("Cara Lee", allow_duplicate=True)

    assert set_person_next_step(person, "", None)["logged"] is False
    assert _state(person)[1] == []
    assert set_person_next_step(999999, "x", None) is None


def test_a_date_without_a_step_is_refused(clean_database):
    person = save_person("Dora Ost", allow_duplicate=True)
    with pytest.raises(ValueError):
        set_person_next_step(person, " ", date(2026, 10, 15))
    assert _state(person) == ((None, None), [])
