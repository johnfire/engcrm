"""Filtering people by stage and the user's own rating together, on the real schema."""
import pytest

from gcrm.db.connection import db
from gcrm.tools.db_people import get_people, save_person, set_person_value_rating

pytestmark = pytest.mark.integration


def _user(email: str) -> tuple[int, int]:
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug = 'default'")
        workspace_id = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO users (email, password_hash, role, workspace_id) "
                       "VALUES (%s, 'hash', 'admin', %s) RETURNING id", (email, workspace_id))
        return cursor.fetchone()["id"], workspace_id


def test_candidates_rated_3_or_better_by_me(clean_database, monkeypatch):
    monkeypatch.setattr("gcrm.tools.db_people.geocode", lambda city, country: None)
    me, workspace = _user("me@example.test")
    other, _ = _user("other@example.test")
    people = {name: save_person(name, pipeline_stage=stage, allow_duplicate=True)
              for name, stage in [("A best", "candidate"), ("B medium", "candidate"), ("C low", "candidate"),
                                  ("D best but prospect", "prospect"), ("E unrated", "candidate"),
                                  ("F rated by someone else", "candidate")]}
    for name, rating in [("A best", 1), ("B medium", 3), ("C low", 4), ("D best but prospect", 1)]:
        set_person_value_rating(me, workspace, people[name], rating)
    set_person_value_rating(other, workspace, people["F rated by someone else"], 1)

    found = get_people(user_id=me, stage="candidate", value_rating="3+", sort="value_rating", dir="asc")

    assert [p["name"] for p in found] == ["A best", "B medium"]
    assert [p["value_rating"] for p in found] == [1, 3]
