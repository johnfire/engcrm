"""Month and since-start counts of contacted people and organizations, on real Postgres."""
import uuid
from datetime import date

import pytest

from gcrm.db.connection import db
from gcrm.tools.db_contact_counts import BUSINESS_START, get_contact_counts

pytestmark = pytest.mark.integration
TODAY = date(2026, 10, 20)


@pytest.fixture
def workspace(clean_database):
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug='default'")
        return cursor.fetchone()["id"]


def organization(cursor, name, workspace_id, deleted=False):
    cursor.execute("INSERT INTO contacts (name,workspace_id,deleted_at) VALUES (%s,%s,%s) RETURNING id",
                   (name, workspace_id, "2026-10-01" if deleted else None))
    return cursor.fetchone()["id"]


def person(cursor, name, workspace_id, organization_id=None):
    cursor.execute("INSERT INTO people (name,workspace_id,contact_id) VALUES (%s,%s,%s) RETURNING id",
                   (name, workspace_id, organization_id))
    return cursor.fetchone()["id"]


def organization_contact(cursor, organization_id, day, method="in_person"):
    cursor.execute("INSERT INTO interactions (contact_id,interaction_date,method,summary) VALUES (%s,%s,%s,'x')",
                   (organization_id, day, method))


def person_contact(cursor, person_id, day, method="visit"):
    cursor.execute("INSERT INTO people_interactions (person_id,occurred_at,method,note) "
                   "VALUES (%s,(%s::date + TIME '12:00') AT TIME ZONE 'Europe/Berlin',%s,'x')", (person_id, day, method))


def test_counts_distinct_people_and_organizations_for_month_and_since_start(workspace):
    with db() as connection:
        cursor = connection.cursor()
        acme = organization(cursor, "Acme", workspace)
        ann = person(cursor, "Ann", workspace, acme)
        organization_contact(cursor, acme, date(2026, 10, 5))
        organization_contact(cursor, acme, date(2026, 10, 9))          # same business twice counts once
        person_contact(cursor, ann, date(2026, 10, 9))
        via_person = organization(cursor, "Via Person GmbH", workspace)  # reached only through Bob
        bob = person(cursor, "Bob", workspace, via_person)
        person_contact(cursor, bob, date(2026, 10, 12))
        solo = person(cursor, "Solo", workspace)                         # no business
        person_contact(cursor, solo, date(2026, 10, 13))
        organization_contact(cursor, organization(cursor, "Last Month", workspace), date(2026, 9, 28))
        organization_contact(cursor, organization(cursor, "Before Start", workspace), date(2026, 9, 30))
        organization_contact(cursor, organization(cursor, "Plan Only", workspace), date(2026, 10, 10), "next_step")
        organization_contact(cursor, organization(cursor, "Gone", workspace, deleted=True), date(2026, 10, 10))
        person(cursor, "Never Met", workspace)
    counts = get_contact_counts(workspace, TODAY)
    assert counts["month"] == {"people": 3, "organizations": 2}
    assert counts["since_start"] == counts["month"]
    assert counts["business_start"] == BUSINESS_START.isoformat() == "2026-10-01"
    assert counts["previous_months"] == [
        {"month_start": "2026-09-01", "month_end": "2026-09-30", "people": 0, "organizations": 2},
        {"month_start": "2026-08-01", "month_end": "2026-08-31", "people": 0, "organizations": 0},
    ]


def test_month_resets_but_since_start_keeps_counting(workspace):
    with db() as connection:
        cursor = connection.cursor()
        acme = organization(cursor, "Acme", workspace)
        person_contact(cursor, person(cursor, "Ann", workspace, acme), date(2026, 10, 14))
    november = get_contact_counts(workspace, date(2026, 11, 3))
    assert november["month"] == {"people": 0, "organizations": 0}
    assert november["since_start"] == {"people": 1, "organizations": 1}
    assert november["previous_months"][0] == {
        "month_start": "2026-10-01", "month_end": "2026-10-31", "people": 1, "organizations": 1,
    }


def test_other_workspaces_are_not_counted(workspace):
    slug = f"other-{uuid.uuid4().hex[:8]}"
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("INSERT INTO workspaces (slug,name) VALUES (%s,'Other') RETURNING id", (slug,))
        other = cursor.fetchone()["id"]
    try:
        with db() as connection:
            organization_contact(connection.cursor(), organization(connection.cursor(), "Theirs", other), date(2026, 10, 6))
        assert get_contact_counts(workspace, TODAY)["month"] == {"people": 0, "organizations": 0}
        assert get_contact_counts(other, TODAY)["month"] == {"people": 0, "organizations": 1}
        assert get_contact_counts(workspace, date(2026, 11, 5))["previous_months"][0]["organizations"] == 0
        assert get_contact_counts(other, date(2026, 11, 5))["previous_months"][0]["organizations"] == 1
    finally:
        with db() as connection:
            cursor = connection.cursor()
            cursor.execute("DELETE FROM interactions WHERE contact_id IN (SELECT id FROM contacts WHERE workspace_id=%s)", (other,))
            cursor.execute("DELETE FROM contacts WHERE workspace_id=%s", (other,))
            cursor.execute("DELETE FROM workspaces WHERE id=%s", (other,))


def test_previous_months_count_unique_contacts_at_both_month_boundaries(workspace):
    with db() as connection:
        cursor = connection.cursor()
        acme = organization(cursor, "Boundary company", workspace)
        ann = person(cursor, "Ann", workspace, acme)
        for day in [date(2026, 9, 1), date(2026, 9, 30), date(2026, 10, 1), date(2026, 10, 31)]:
            person_contact(cursor, ann, day)
            organization_contact(cursor, acme, day)
        organization_contact(cursor, organization(cursor, "Too old", workspace), date(2026, 8, 31))
        organization_contact(cursor, organization(cursor, "Current month", workspace), date(2026, 11, 1))
        organization_contact(cursor, organization(cursor, "Plan only", workspace), date(2026, 10, 5), "next_step")
        organization_contact(cursor, organization(cursor, "Deleted", workspace, deleted=True), date(2026, 9, 5))
    counts = get_contact_counts(workspace, date(2026, 11, 5))
    assert counts["previous_months"] == [
        {"month_start": "2026-10-01", "month_end": "2026-10-31", "people": 1, "organizations": 1},
        {"month_start": "2026-09-01", "month_end": "2026-09-30", "people": 1, "organizations": 1},
    ]
    assert counts["month"] == {"people": 0, "organizations": 1}


def test_previous_months_respect_the_selected_offer(workspace):
    with db() as connection:
        cursor = connection.cursor()
        for slug in ["consulting", "learnwohl"]:
            company = organization(cursor, slug, workspace)
            cursor.execute("INSERT INTO interactions (contact_id,interaction_date,method,offer_id) "
                           "SELECT %s,'2026-10-15','phone',id FROM offers WHERE workspace_id=%s AND slug=%s",
                           (company, workspace, slug))
    all_offers = get_contact_counts(workspace, date(2026, 11, 5))
    consulting = get_contact_counts(workspace, date(2026, 11, 5), offer="consulting")
    assert all_offers["previous_months"][0]["organizations"] == 2
    assert consulting["previous_months"][0]["organizations"] == 1


def test_first_day_is_included_at_berlin_midnight(workspace):
    with db() as connection:
        cursor = connection.cursor()
        company = organization(cursor, "First day", workspace)
        colleague = person(cursor, "Midnight", workspace, company)
        organization_contact(cursor, company, date(2026, 10, 1))
        cursor.execute("INSERT INTO people_interactions (person_id,occurred_at,method,note) "
                       "VALUES (%s,'2026-09-30T22:00:00Z','visit','Midnight contact')", (colleague,))
        before = person(cursor, "Too early", workspace)
        cursor.execute("INSERT INTO people_interactions (person_id,occurred_at,method,note) "
                       "VALUES (%s,'2026-09-30T21:59:59Z','visit','Before start')", (before,))
        person_contact(cursor, colleague, date(2026, 11, 1))
        organization_contact(cursor, company, date(2026, 11, 1))
    counts = get_contact_counts(workspace, date(2026, 11, 6))
    assert counts["previous_months"][0]["people"] == 1
    assert counts["previous_months"][0]["organizations"] == 1
    assert counts["month"] == {"people": 1, "organizations": 1}
    assert counts["since_start"] == {"people": 1, "organizations": 1}
