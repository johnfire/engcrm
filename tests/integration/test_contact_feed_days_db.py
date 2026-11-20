"""The feed's Days column against actual PostgreSQL: first contact to customer, or to today."""
from datetime import date, timedelta

import pytest

from gcrm.db.connection import db
from gcrm.tools.db_contact_feed import DAYS_SQL, get_contact_feed, get_stage_means
from gcrm.tools.db_contact_feed_query import contact_feed_sql
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


def _names(workspace, **options):
    return [row["name"] for row in get_contact_feed(workspace_id=workspace, **options)]


def test_the_sql_days_are_the_days_on_screen(days_contacts):
    """Sorting and averaging use DAYS_SQL; the column shows days_to_customer. They must agree on every row."""
    shown = _by_name(days_contacts)
    query = contact_feed_sql(columns=f"name, {DAYS_SQL} AS days") + " WHERE workspace_id = %s"
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute(query, [None, None, days_contacts])
        in_sql = {row["name"]: row["days"] for row in cursor.fetchall()}
    assert in_sql == {name: row["days_to_customer"] for name, row in shown.items()}
    assert in_sql["Suspect AG"] is None and in_sql["Prospect GmbH"] == 30


def test_sorting_by_days_puts_the_blanks_last_in_either_direction(days_contacts):
    # 30, then the two 20s in id order, then 8, then the suspect that has no figure
    assert _names(days_contacts, sort="days") == ["Prospect GmbH", "Customer KG", "Linked Prospect", "Solo Sam", "Suspect AG"]
    assert _names(days_contacts, sort="days", dir="asc") == ["Solo Sam", "Customer KG", "Linked Prospect", "Prospect GmbH", "Suspect AG"]


def test_first_contact_sorts_newest_first_by_default(days_contacts):
    # Solo Sam began 8 days ago, Linked Prospect 20 days ago (its person's contact), the other three 30 days ago.
    # Suspect AG has a first contact too: it only has no Days figure, because "suspect" is not a measured stage.
    names = _names(days_contacts, sort="first_contact")
    assert names[:2] == ["Solo Sam", "Linked Prospect"]
    assert set(names[2:]) == {"Suspect AG", "Prospect GmbH", "Customer KG"}
    assert _names(days_contacts, sort="first_contact", dir="asc")[-2:] == ["Linked Prospect", "Solo Sam"]


def test_a_second_sort_orders_within_the_first_and_never_reorders_it(days_contacts):
    plain = _names(days_contacts, sort="pipeline_stage", dir="asc")
    assert plain.index("Prospect GmbH") < plain.index("Linked Prospect")           # tie: by id
    youngest = _names(days_contacts, sort="pipeline_stage", dir="asc", then="days", then_dir="asc")
    oldest = _names(days_contacts, sort="pipeline_stage", dir="asc", then="days", then_dir="desc")
    assert youngest.index("Linked Prospect") < youngest.index("Prospect GmbH")     # 20 before 30
    assert oldest.index("Prospect GmbH") < oldest.index("Linked Prospect")         # 30 before 20
    # the stage blocks themselves stay where they were: only the order inside the prospects changed
    assert [n for n in youngest if n not in ("Prospect GmbH", "Linked Prospect")] == \
           [n for n in plain if n not in ("Prospect GmbH", "Linked Prospect")]
    assert sorted(youngest[youngest.index("Linked Prospect"):][:2]) == ["Linked Prospect", "Prospect GmbH"]


def test_the_mean_days_per_stage_leaves_out_contacts_with_no_figure(days_contacts):
    means = get_stage_means(workspace_id=days_contacts)
    by_stage = {row["stage"]: row for row in means["stages"]}
    assert [row["stage"] for row in means["stages"]] == ["nibble", "prospect", "opportunity", "customer"]
    assert (by_stage["nibble"]["contacts"], by_stage["nibble"]["counted"], by_stage["nibble"]["mean"]) == (1, 1, 8)
    assert (by_stage["prospect"]["contacts"], by_stage["prospect"]["counted"], by_stage["prospect"]["mean"]) == (2, 2, 25)  # (30 + 20) / 2
    assert by_stage["opportunity"] == {"stage": "opportunity", "contacts": 0, "counted": 0, "mean": None}
    assert (by_stage["customer"]["counted"], by_stage["customer"]["mean"]) == (1, 20)
    # Suspect AG is not at a measured stage, so it is in no row; all four: (8 + 30 + 20 + 20) / 4 = 19.5 -> 20
    assert (means["all"]["contacts"], means["all"]["counted"], means["all"]["mean"]) == (4, 4, 20)


def test_a_measured_contact_with_no_first_contact_day_is_not_averaged(days_contacts):
    with db() as connection:
        cursor = connection.cursor()
        # Prospect GmbH keeps a prospect deal and a "contacted" status but loses its dated contact
        cursor.execute("DELETE FROM interactions WHERE contact_id = 2")
        cursor.execute("UPDATE deals SET status = 'contacted' WHERE contact_id = 2")
    prospects = {row["stage"]: row for row in get_stage_means(workspace_id=days_contacts)["stages"]}["prospect"]
    assert (prospects["contacts"], prospects["counted"], prospects["mean"]) == (2, 1, 20)   # only Linked Prospect's 20


def test_the_stage_means_follow_the_search_and_ignore_the_stage_filter(days_contacts):
    only = get_stage_means(workspace_id=days_contacts, search="Prospect GmbH")
    assert only["all"]["contacts"] == 1 and only["all"]["mean"] == 30
    assert {row["stage"]: row["contacts"] for row in only["stages"]}["prospect"] == 1
