"""Month and since-start counts of contacted people and organizations, on real Postgres."""
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


def test_month_resets_but_since_start_keeps_counting(workspace):
    with db() as connection:
        cursor = connection.cursor()
        acme = organization(cursor, "Acme", workspace)
        person_contact(cursor, person(cursor, "Ann", workspace, acme), date(2026, 10, 14))
    november = get_contact_counts(workspace, date(2026, 11, 3))
    assert november["month"] == {"people": 0, "organizations": 0}
    assert november["since_start"] == {"people": 1, "organizations": 1}


def test_other_workspaces_are_not_counted(workspace):
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("INSERT INTO workspaces (slug,name) VALUES ('other','Other') RETURNING id")
        other = cursor.fetchone()["id"]
        organization_contact(cursor, organization(cursor, "Theirs", other), date(2026, 10, 6))
    assert get_contact_counts(workspace, TODAY)["month"] == {"people": 0, "organizations": 0}
