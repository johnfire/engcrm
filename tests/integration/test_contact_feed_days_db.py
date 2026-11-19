"""The feed's Days column against actual PostgreSQL: first contact to customer, or to today."""
from datetime import date, timedelta

import pytest

from gcrm.db.connection import db
from gcrm.tools.db_contact_feed import get_contact_feed
from gcrm.tools.db_deals import set_organization_deal, set_person_stage

pytestmark = pytest.mark.integration

TODAY = date.today()


def _days_ago(n: int) -> date:
    return TODAY - timedelta(days=n)


@pytest.fixture
def days_contacts(clean_database):
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug='default'")
        workspace = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO contacts (id,name,city,workspace_id) VALUES "
                       "(1,'Suspect AG','A',%s),(2,'Prospect GmbH','A',%s),"
                       "(3,'Customer KG','A',%s),(4,'Linked Prospect','A',%s)",
                       (workspace, workspace, workspace, workspace))
        for contact_id, stage in ((1, "suspect"), (2, "prospect"), (3, "prospect"), (4, "prospect")):
            set_organization_deal(cursor, contact_id, stage=stage)
        cursor.execute("INSERT INTO people (id,name,contact_id,workspace_id) VALUES "
                       "(1,'Linked Lena',4,%s),(2,'Solo Sam',NULL,%s)", (workspace, workspace))
        set_person_stage(cursor, 1, "prospect")
        set_person_stage(cursor, 2, "nibble")
        for contact_id in (1, 2, 3):
            cursor.execute("INSERT INTO interactions (contact_id,interaction_date,method) VALUES (%s,%s,'email'),(%s,%s,'email')",
                           (contact_id, _days_ago(30), contact_id, _days_ago(2)))
        # The organization's own first activity is recent; its person was contacted earlier.
        cursor.execute("INSERT INTO interactions (contact_id,interaction_date,method) VALUES (4,%s,'email')", (_days_ago(5),))
        cursor.execute("INSERT INTO people_interactions (person_id,occurred_at,method,note) VALUES "
                       "(1,now() - interval '20 days','email','first'),(2,now() - interval '8 days','email','solo')")
        # Customer: stage change recorded 10 days ago.
        set_organization_deal(cursor, 3, stage="customer")
        cursor.execute("UPDATE stage_changes SET changed_at = now() - interval '10 days' "
                       "WHERE entity_type='organization' AND entity_id=3 AND to_stage='customer'")
    return workspace


def _by_name(workspace):
    rows = get_contact_feed(workspace_id=workspace)
    return {row["name"]: row for row in rows}


def test_days_to_customer_or_today(days_contacts):
    rows = _by_name(days_contacts)
    assert rows["Suspect AG"]["days_to_customer"] is None
    assert rows["Prospect GmbH"]["days_to_customer"] == 30
    assert rows["Customer KG"]["days_to_customer"] == 20


def test_organization_counts_from_its_people_earlier_contact(days_contacts):
    assert _by_name(days_contacts)["Linked Prospect"]["days_to_customer"] == 20


def test_standalone_person_is_measured_too(days_contacts):
    assert _by_name(days_contacts)["Solo Sam"]["days_to_customer"] == 8
