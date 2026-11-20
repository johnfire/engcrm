"""LinkedIn message (work I did) and LinkedIn reply (their answer, not work) against the real schema."""
from datetime import date

import pytest

from gcrm.activity_types import ACTIVITY_TYPES, DEFAULT_MINUTES
from gcrm.db.connection import db
from gcrm.tools.db_contact_feed import get_contact_feed
from gcrm.tools.db_interactions import log_meeting_note
from gcrm.tools.db_organizations import save_organization
from gcrm.tools.db_people import save_person
from gcrm.tools.statistics import get_minute_defaults, get_statistics, set_minute_defaults

pytestmark = pytest.mark.integration

WEEK = (date(2026, 10, 12), date(2026, 10, 18))
SENT, ANSWERED = date(2026, 10, 13), date(2026, 10, 14)


@pytest.fixture
def world(clean_database, monkeypatch):
    monkeypatch.setattr("gcrm.tools.db_organizations.geocode", lambda city, country: None)
    monkeypatch.setattr("gcrm.tools.db_people.geocode", lambda city, country: None)
    organization = save_organization("LinkedIn Firm", "Augsburg", pipeline_stage="nibble", source="test_fixture")
    person = save_person("Pat Example", contact_id=organization, allow_duplicate=True, source="test_fixture")
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug = 'default'")
        workspace = cursor.fetchone()["id"]
    return {"organization": organization, "person": person, "workspace": workspace}


def _person_activity(person_id: int, day: date, method: str):
    with db() as connection:
        connection.cursor().execute(
            "INSERT INTO people_interactions (person_id, occurred_at, method, note) VALUES (%s, %s, %s, 'x')",
            (person_id, day, method))


def test_minutes_can_be_saved_for_every_work_type(world):
    """The minutes table once allowed only six types, so post_mail (and now linkedin) could not be saved."""
    set_minute_defaults(world["workspace"], {kind: 7 for kind in ACTIVITY_TYPES})
    assert get_minute_defaults(world["workspace"]) == {kind: 7 for kind in ACTIVITY_TYPES}


def test_a_linkedin_message_is_work_with_a_default_of_five_minutes(world):
    assert DEFAULT_MINUTES["linkedin"] == 5
    log_meeting_note(world["organization"], "linkedin", "Opener A", occurred_on=SENT)
    _person_activity(world["person"], SENT, "linkedin")
    effort = get_statistics(world["workspace"], *WEEK, today=date(2026, 10, 15))["current"]
    assert (effort["effort"]["linkedin"]["count"], effort["effort"]["linkedin"]["minutes"]) == (2, 10)


def test_a_reply_is_not_work_so_it_is_left_out_of_effort(world):
    log_meeting_note(world["organization"], "linkedin", "Opener A", occurred_on=SENT)
    log_meeting_note(world["organization"], "linkedin_reply", "They answered", occurred_on=ANSWERED)
    _person_activity(world["person"], ANSWERED, "linkedin_reply")
    current = get_statistics(world["workspace"], *WEEK, today=date(2026, 10, 15))["current"]
    assert "linkedin_reply" not in current["effort"]
    assert (current["activities"], current["minutes"]) == (1, 5)             # only the message I sent


def test_both_count_as_contact_days_in_the_contact_list(world):
    log_meeting_note(world["organization"], "linkedin", "Opener A", occurred_on=SENT)
    log_meeting_note(world["organization"], "linkedin_reply", "They answered", occurred_on=ANSWERED)
    row = next(r for r in get_contact_feed(workspace_id=world["workspace"]) if r["kind"] == "organization")
    assert (row["first_contact"], row["last_contact"]) == ("2026-10-13", "2026-10-14")


def test_the_web_forms_log_both_and_show_their_names(world):
    from fastapi.testclient import TestClient

    import gcrm.api.main as main
    from gcrm.api.security import hash_password
    with db() as connection:
        connection.cursor().execute(
            "INSERT INTO users (email, name, password_hash, role, workspace_id, is_active) "
            "VALUES ('linkedin@example.test', 'linkedin', %s, 'admin', %s, TRUE)",
            (hash_password("a-long-test-password-1"), world["workspace"]))
    browser = TestClient(main.app)
    assert browser.post("/login", data={"email": "linkedin@example.test", "password": "a-long-test-password-1"},
                        follow_redirects=False).status_code in (302, 303)
    url = f"/organizations/{world['organization']}"
    for method, note in (("linkedin", "Sent opener A"), ("linkedin_reply", "They said yes")):
        assert browser.post(f"{url}/activity", data={"method": method, "note": note},
                            follow_redirects=False).status_code == 303
    assert browser.post(f"{url}/activity", data={"method": "linkedin_spam", "note": "x"},
                        follow_redirects=False).status_code == 400
    page = browser.get(f"{url}?lang=en").text
    assert page.count("LinkedIn message") >= 2 and page.count("LinkedIn reply") >= 2   # the choice, and the history row
    from gcrm.i18n import (
        translate,  # a signed-in account's own language wins over ?lang=, so check the labels directly
    )
    assert translate("activity.linkedin", "de") == "LinkedIn-Nachricht" and translate("activity.linkedin_reply", "de") == "LinkedIn-Antwort"
    person = browser.get(f"/people/{world['person']}?lang=en").text
    assert 'value="linkedin"' in person and 'value="linkedin_reply"' in person
