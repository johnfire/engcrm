"""Visit details on logged activities, against the real schema."""
import pathlib
from datetime import date

import psycopg2
import pytest

from gcrm.db.connection import db
from gcrm.tools.db_interactions import get_visit_summary, log_meeting_note

pytestmark = pytest.mark.integration


def _organization() -> int:
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("INSERT INTO contacts (name, workspace_id) "
                       "SELECT 'Visit Venue', id FROM workspaces WHERE slug = 'default' RETURNING id")
        return cursor.fetchone()["id"]


def test_summary_is_read_from_the_logged_activities(clean_database):
    contact_id = _organization()
    assert get_visit_summary(contact_id) == {
        "last_visited": None, "last_visit_minutes": None, "first_attitude": None, "last_attitude": None,
        "last_my_read": None, "materials_left": None, "followup_promised": None}

    log_meeting_note(contact_id, "in_person", "First drop-in", occurred_on=date(2026, 10, 1),
                     duration_minutes=15, attitude=["skeptical"], my_read=["cant_tell"], materials_left="flyer")
    log_meeting_note(contact_id, "phone", "Called back", occurred_on=date(2026, 10, 10),
                     attitude=["neutral"], my_read=["holding_back", "nh"],
                     follow_up_text="send price list", follow_up_date=date(2026, 11, 1))
    log_meeting_note(contact_id, "meeting", "Sat down with the owner", occurred_on=date(2026, 10, 20),
                     duration_minutes=45, attitude=["warm", "skeptical"])
    # Logged later, but it happened earlier: the date decides, not the order of logging.
    log_meeting_note(contact_id, "in_person", "Forgot to log this one", occurred_on=date(2026, 9, 15))

    assert get_visit_summary(contact_id) == {
        "last_visited": date(2026, 10, 20), "last_visit_minutes": 45, "first_attitude": ["skeptical"],
        "last_attitude": ["warm", "skeptical"], "last_my_read": ["holding_back", "nh"],
        "materials_left": "flyer", "followup_promised": "send price list"}


def test_blank_date_is_today_and_unknown_judgments_are_refused(clean_database):
    contact_id = _organization()
    note_id = log_meeting_note(contact_id, None, "Plain note")
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT interaction_date, attitude, my_read FROM interactions WHERE id = %s", (note_id,))
        assert dict(cursor.fetchone()) == {"interaction_date": date.today(), "attitude": None, "my_read": None}

    # The database refuses unknown values even if a caller skips parse_choices.
    with pytest.raises(psycopg2.errors.CheckViolation):
        log_meeting_note(contact_id, None, "Bad", attitude=["warm", "ecstatic"])
    with pytest.raises(psycopg2.errors.CheckViolation):
        log_meeting_note(contact_id, None, "Bad", my_read=["liar"])


def test_person_activities_carry_both_judgments(clean_database):
    from gcrm.tools.db_people_interactions import get_person_interactions, log_person_note

    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("INSERT INTO people (name, workspace_id) "
                       "SELECT 'Bea', id FROM workspaces WHERE slug = 'default' RETURNING id")
        person_id = cursor.fetchone()["id"]
    log_person_note(person_id, "call", "Odd call", attitude=["cold"], my_read=["story_doesnt_add_up", "cf"])
    [entry] = get_person_interactions(person_id)
    assert (entry["attitude"], entry["my_read"]) == (["cold"], ["story_doesnt_add_up", "cf"])
    with pytest.raises(psycopg2.errors.CheckViolation):
        log_person_note(person_id, "call", "Bad", my_read=["nope"])


def test_migration_copied_each_old_impression_into_attitude(clean_database):
    contact_id = _organization()
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("INSERT INTO interactions (contact_id, interaction_date, method, impression) "
                       "VALUES (%s, '2026-10-01', 'phone', 'cold') RETURNING id", (contact_id,))
        old_id = cursor.fetchone()["id"]
        cursor.execute((pathlib.Path(__file__).parents[2] / "gcrm/db/migrations/072_attitude_and_my_read.sql").read_text())
        cursor.execute("SELECT impression, attitude FROM interactions WHERE id = %s", (old_id,))
        assert dict(cursor.fetchone()) == {"impression": "cold", "attitude": ["cold"]}
