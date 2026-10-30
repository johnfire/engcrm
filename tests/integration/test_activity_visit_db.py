"""Visit details on logged activities, against the real schema."""
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
        "last_visited": None, "last_visit_minutes": None, "first_impression": None,
        "last_impression": None, "materials_left": None, "followup_promised": None}

    log_meeting_note(contact_id, "in_person", "First drop-in", occurred_on=date(2026, 10, 1),
                     duration_minutes=15, impression="skeptical", materials_left="flyer")
    log_meeting_note(contact_id, "phone", "Called back", occurred_on=date(2026, 10, 10),
                     impression="neutral", follow_up_text="send price list", follow_up_date=date(2026, 11, 1))
    log_meeting_note(contact_id, "meeting", "Sat down with the owner", occurred_on=date(2026, 10, 20),
                     duration_minutes=45, impression="warm")
    # Logged later, but it happened earlier: the date decides, not the order of logging.
    log_meeting_note(contact_id, "in_person", "Forgot to log this one", occurred_on=date(2026, 9, 15))

    assert get_visit_summary(contact_id) == {
        "last_visited": date(2026, 10, 20), "last_visit_minutes": 45, "first_impression": "skeptical",
        "last_impression": "warm", "materials_left": "flyer", "followup_promised": "send price list"}


def test_blank_date_is_today_and_unknown_impressions_are_refused(clean_database):
    contact_id = _organization()
    note_id = log_meeting_note(contact_id, None, "Plain note")
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT interaction_date, impression FROM interactions WHERE id = %s", (note_id,))
        assert dict(cursor.fetchone()) == {"interaction_date": date.today(), "impression": None}

    with pytest.raises(psycopg2.errors.CheckViolation):
        log_meeting_note(contact_id, None, "Bad", impression="ecstatic")
