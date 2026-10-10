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
    keep_id = save_person("Anna Huber", email="anna@example.test", title="CEO", notes="Met at fair.",
                          pipeline_stage="prospect", source="test_fixture")
    drop_id = save_person("Anna Huber", phone="0821 1234", title="Managing Director",
                          notes="LinkedIn import.", pipeline_stage="customer", allow_duplicate=True,
                          source="test_fixture")
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
        cursor.execute("INSERT INTO contacts (name, workspace_id) VALUES ('Huber GmbH', %s) "
                       "RETURNING id", (workspace_id,))
        contact_id = cursor.fetchone()["id"]
        # Both have a Consulting deal (they clash); only the duplicate has a LearnWohl deal,
        # and the duplicate is the contact person on Huber GmbH's Consulting deal.
        cursor.execute("UPDATE deals SET next_step = 'Send the offer' WHERE person_id = %s", (drop_id,))
        cursor.execute("INSERT INTO deals (workspace_id, offer_id, person_id, pipeline_stage) "
                       "VALUES (%s, offer_id_for(%s, 'learnwohl'), %s, 'suspect')",
                       (workspace_id, workspace_id, drop_id))
        cursor.execute("INSERT INTO deals (workspace_id, offer_id, contact_id, contact_person_id) "
                       "VALUES (%s, offer_id_for(%s, 'consulting'), %s, %s)",
                       (workspace_id, workspace_id, contact_id, drop_id))
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


def _deals_of(person_id: int) -> tuple[list, list]:
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT o.slug, d.pipeline_stage, d.next_step FROM deals d JOIN offers o ON o.id = d.offer_id "
                       "WHERE d.person_id = %s AND d.deleted_at IS NULL ORDER BY o.slug", (person_id,))
        owned = [tuple(row.values()) for row in cursor.fetchall()]
        cursor.execute("SELECT contact_id FROM deals WHERE contact_person_id = %s", (person_id,))
        contact_for = [row["contact_id"] for row in cursor.fetchall()]
        return owned, contact_for


def test_deals_move_and_a_clash_keeps_the_kept_persons_deal_and_notes_the_other(clean_database):
    ids = _setup_pair()

    merge_people(ids["keep"], ids["drop"], apply=True, today=date(2026, 10, 5))

    owned, contact_for = _deals_of(ids["keep"])
    assert owned == [("consulting", "prospect", None), ("learnwohl", "suspect", None)]
    assert len(contact_for) == 1  # now the contact person on Huber GmbH's deal
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT notes FROM people WHERE id = %s", (ids["keep"],))
        notes = cursor.fetchone()["notes"]
    assert "Deal not carried over" in notes and "stage customer" in notes and "Send the offer" in notes


def test_a_second_run_is_refused_because_the_duplicate_is_gone(clean_database):
    ids = _setup_pair()
    merge_people(ids["keep"], ids["drop"], apply=True)

    with pytest.raises(MergeRefused):
        merge_people(ids["keep"], ids["drop"], apply=True)
