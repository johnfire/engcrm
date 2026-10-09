"""Merging a duplicate person against the real schema: every linked row moves,
the duplicate is gone, and a preview writes nothing."""
from datetime import date

import pytest

from gcrm.db.connection import db
from gcrm.tools.db_people import save_person
from gcrm.tools.db_people_interactions import log_person_note
from gcrm.tools.people_merge import MergeRefused, merge_people

pytestmark = pytest.mark.integration


def _setup_pair() -> dict:
    keep_id = save_person("Anna Huber", email="anna@example.test", title="CEO", notes="Met at fair.", source="test_fixture")
    drop_id = save_person("Anna Huber", phone="0821 1234", title="Managing Director",
                          notes="LinkedIn import.", allow_duplicate=True, source="test_fixture")
    log_person_note(keep_id, "typed", "kept note")
    log_person_note(drop_id, "typed", "duplicate note")
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug = 'default'")
        workspace_id = cursor.fetchone()["id"]
        cursor.execute(
            "INSERT INTO users (email, password_hash, role, workspace_id) VALUES "
            "('merge-one@example.test', 'hash', 'spectator', %s), "
            "('merge-two@example.test', 'hash', 'spectator', %s) RETURNING id",
            (workspace_id, workspace_id),
        )
        user_one, user_two = (row["id"] for row in cursor.fetchall())
        cursor.execute(
            "INSERT INTO person_user_priorities (workspace_id, user_id, person_id, priority) VALUES "
            "(%s, %s, %s, 2), (%s, %s, %s, 4), (%s, %s, %s, 5)",
            (workspace_id, user_one, keep_id, workspace_id, user_one, drop_id, workspace_id, user_two, drop_id),
        )
        cursor.execute("INSERT INTO contacts (name, status, workspace_id) VALUES ('Huber GmbH', 'cold', %s) "
                       "RETURNING id", (workspace_id,))
        contact_id = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO person_match_rejections (person_id, contact_id) VALUES (%s, %s), (%s, %s)",
                       (keep_id, contact_id, drop_id, contact_id))
        cursor.execute("INSERT INTO approval_queue (person_id, draft_subject, draft_body) "
                       "VALUES (%s, 'Hallo', 'Body')", (drop_id,))
    return {"keep": keep_id, "drop": drop_id, "user_one": user_one, "user_two": user_two}


def _counts(person_id: int) -> dict:
    with db() as connection:
        cursor = connection.cursor()
        counts = {}
        for table in ("people", "people_interactions", "person_user_priorities",
                      "person_match_rejections", "approval_queue"):
            column = "id" if table == "people" else "person_id"
            cursor.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE {column} = %s", (person_id,))
            counts[table] = cursor.fetchone()["n"]
        return counts


def test_preview_writes_nothing(clean_database):
    ids = _setup_pair()
    before = (_counts(ids["keep"]), _counts(ids["drop"]))

    report = merge_people(ids["keep"], ids["drop"], apply=False)

    assert report["applied"] is False
    assert report["conflicts"] == ["title: Managing Director"]
    assert (_counts(ids["keep"]), _counts(ids["drop"])) == before


def test_apply_moves_everything_and_removes_the_duplicate(clean_database):
    ids = _setup_pair()

    merge_people(ids["keep"], ids["drop"], apply=True, today=date(2026, 10, 5))

    assert _counts(ids["drop"]) == {"people": 0, "people_interactions": 0, "person_user_priorities": 0,
                                    "person_match_rejections": 0, "approval_queue": 0}
    assert _counts(ids["keep"]) == {"people": 1, "people_interactions": 2, "person_user_priorities": 2,
                                    "person_match_rejections": 1, "approval_queue": 1}
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT * FROM people WHERE id = %s", (ids["keep"],))
        kept = cursor.fetchone()
        cursor.execute("SELECT user_id, priority FROM person_user_priorities WHERE person_id = %s ORDER BY user_id",
                       (ids["keep"],))
        ratings = [(row["user_id"], row["priority"]) for row in cursor.fetchall()]
    assert kept["email"] == "anna@example.test" and kept["phone"] == "0821 1234" and kept["title"] == "CEO"
    assert "LinkedIn import." in kept["notes"] and "title: Managing Director" in kept["notes"]
    assert "rated #" in kept["notes"]
    assert ratings == [(ids["user_one"], 2), (ids["user_two"], 5)]


def test_a_second_run_is_refused_because_the_duplicate_is_gone(clean_database):
    ids = _setup_pair()
    merge_people(ids["keep"], ids["drop"], apply=True)

    with pytest.raises(MergeRefused):
        merge_people(ids["keep"], ids["drop"], apply=True)
