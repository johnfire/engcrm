"""Mixed chronology and pagination against actual PostgreSQL."""
import pytest

from gcrm.db.connection import db
from gcrm.tools.db_contact_feed import get_contact_feed
from gcrm.tools.db_deals import set_organization_deal, set_person_stage

pytestmark = pytest.mark.integration


@pytest.fixture
def mixed_contacts(clean_database):
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug='default'")
        workspace_id = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO workspaces (name,slug) VALUES ('Other feed workspace','contact-feed-test') "
                       "ON CONFLICT (slug) DO UPDATE SET name=EXCLUDED.name RETURNING id")
        other_workspace = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO contacts (id,name,city,workspace_id,created_at) VALUES "
                       "(1,'Academy','Augsburg',%s,'2026-10-05T10:00:00Z'), "
                       "(2,'Other company','Ulm',%s,'2026-10-06T10:00:00Z'), "
                       "(3,'Hidden organization','Ulm',%s,'2026-10-07T10:00:00Z')", (workspace_id, workspace_id, other_workspace))
        for contact_id, stage in ((1, "candidate"), (2, "suspect"), (3, "candidate")):
            set_organization_deal(cursor, contact_id, stage=stage)
        cursor.execute("INSERT INTO people (id,name,title,email,contact_id,workspace_id,created_at) VALUES "
                       "(1,'Ann','Course coordinator','ann@academy.test',1,%s,'2026-10-06T10:00:00Z'), "
                       "(2,'No stage',NULL,NULL,NULL,%s,'2026-10-04T10:00:00Z'), "
                       "(3,'Hidden person',NULL,NULL,3,%s,'2026-10-07T10:00:00Z')", (workspace_id, workspace_id, other_workspace))
        set_person_stage(cursor, 1, "candidate")
        cursor.execute("INSERT INTO people (id,name,contact_id,workspace_id,created_at,deleted_at) "
                       "VALUES (4,'Deleted person',1,%s,NOW(),NOW())", (workspace_id,))
        cursor.execute("INSERT INTO interactions (contact_id,interaction_date,method) VALUES "
                       "(1,'2026-10-03','phone'),(2,'2026-10-05','in_person'),(3,'2026-10-06','phone')")
        cursor.execute("INSERT INTO people_interactions (person_id,occurred_at,method,note) VALUES "
                       "(1,'2026-10-04T10:00:00Z','call','Contact'),(2,'2026-10-02T10:00:00Z','visit','Contact'),"
                       "(3,'2026-10-06T10:00:00Z','call','Hidden'),(4,NOW(),'call','Deleted')")
    return workspace_id, other_workspace


def test_types_share_one_stable_order_and_keep_colliding_ids(mixed_contacts):
    workspace_id, _ = mixed_contacts
    contacts = get_contact_feed(workspace_id=workspace_id)
    assert [(contact['kind'], contact['id']) for contact in contacts] == [
        ('organization', 2), ('organization', 1), ('person', 2),
    ]
    assert contacts[1]['city'] == 'Augsburg'
    assert contacts[1]['people'][0]['description'] == 'Course coordinator'
    assert contacts[1]['people'][0]['id'] == contacts[1]['id'] == 1
    assert contacts[1]['last_contact'] == '2026-10-04'
    assert contacts[1]['last_contact_kind'] == 'person'
    assert contacts[1]['last_contact_id'] == 1
    assert get_contact_feed(workspace_id=workspace_id) == contacts
    assert len(get_contact_feed(workspace_id=workspace_id, kind='person')) == 1
    assert len(get_contact_feed(workspace_id=workspace_id, stage='candidate')) == 1
    assert get_contact_feed(workspace_id=workspace_id, stage='none')[0]['name'] == 'No stage'
    assert get_contact_feed(workspace_id=workspace_id, search='Ann Academy')[0]['name'] == 'Academy'
    assert get_contact_feed(workspace_id=workspace_id, search='ann@academy.test')[0]['kind'] == 'organization'
    assert get_contact_feed(workspace_id=workspace_id, sort='name')[0]['name'] == 'Academy'
    assert get_contact_feed(workspace_id=workspace_id, search='%') == []


def test_deleted_and_cross_workspace_organization_metadata_stay_hidden(mixed_contacts):
    workspace_id, _ = mixed_contacts
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute('UPDATE people SET contact_id=3 WHERE id=1')
    contacts = get_contact_feed(workspace_id=workspace_id)
    assert next(contact for contact in contacts if contact['kind'] == 'person' and contact['id'] == 1)['company'] is None
    assert all('Hidden' not in contact['name'] and 'Deleted' not in contact['name'] for contact in contacts)
    with db() as connection:
        connection.cursor().execute('UPDATE contacts SET deleted_at=NOW() WHERE id=1')
    assert not any(contact['kind'] == 'organization' and contact['id'] == 1 for contact in get_contact_feed(workspace_id=workspace_id))


def test_combined_pagination_selects_global_pages_instead_of_two_partial_lists(mixed_contacts):
    workspace_id, _ = mixed_contacts
    with db() as connection:
        connection.cursor().execute("INSERT INTO people (id,name,workspace_id,created_at) "
                                    "SELECT 10+sequence,'Batch '||sequence,%s,'2026-10-08T10:00:00Z'::timestamptz "
                                    "FROM generate_series(1,60) sequence", (workspace_id,))
        connection.cursor().execute("INSERT INTO people_interactions (person_id,occurred_at,method,note) "
                                    "SELECT 10+sequence,'2026-10-05T10:00:00Z'::timestamptz + sequence*INTERVAL '1 minute',"
                                    "'call','Batch contact' FROM generate_series(1,60) sequence")
    first = get_contact_feed(workspace_id=workspace_id)
    second = get_contact_feed(workspace_id=workspace_id, page=2)
    assert len(first) == 50 and len(second) == 13
    identities = [(contact['kind'], contact['id']) for contact in first + second]
    assert len(set(identities)) == 63
    assert len(get_contact_feed(workspace_id=workspace_id, extra_row=True)) == 51
    assert get_contact_feed(workspace_id=workspace_id, page=3) == []


def test_business_with_only_person_history_appears_and_corrections_reorder_it(mixed_contacts):
    from gcrm.tools.db_contact_dates import get_contact_date, parse_contact_day, set_contact_date

    workspace_id, _ = mixed_contacts
    with db() as connection:
        connection.cursor().execute('DELETE FROM interactions WHERE contact_id=1')
    academy = get_contact_feed(workspace_id=workspace_id, search='Academy')[0]
    assert academy['last_contact'] == '2026-10-04'
    assert academy['last_contact_kind'] == 'person' and academy['last_contact_id'] == 1
    version = get_contact_date('person', 1, workspace_id)
    set_contact_date('person', 1, parse_contact_day('2026-10-01'), version['interaction_id'], version['contact_date'], workspace_id)
    contacts = get_contact_feed(workspace_id=workspace_id)
    assert [contact['name'] for contact in contacts] == ['Other company', 'No stage', 'Academy']
    assert contacts[-1]['last_contact'] == '2026-10-01'


def test_direct_business_history_wins_ties_and_later_contact(mixed_contacts):
    workspace_id, _ = mixed_contacts
    with db() as connection:
        connection.cursor().execute("UPDATE interactions SET interaction_date='2026-10-04' WHERE contact_id=1")
    academy = get_contact_feed(workspace_id=workspace_id, search='Academy')[0]
    assert (academy['last_contact_kind'], academy['last_contact_id']) == ('organization', 1)
    with db() as connection:
        connection.cursor().execute("UPDATE interactions SET interaction_date='2026-10-06' WHERE contact_id=1")
    assert get_contact_feed(workspace_id=workspace_id)[0]['name'] == 'Academy'


def test_linked_people_without_actual_history_are_hidden_and_deleted_business_falls_back(mixed_contacts):
    workspace_id, _ = mixed_contacts
    with db() as connection:
        connection.cursor().execute("INSERT INTO people (id,name,contact_id,workspace_id) VALUES (5,'Planned',1,%s)", (workspace_id,))
        connection.cursor().execute("INSERT INTO people_interactions (person_id,method,note) VALUES (5,'next_step','Plan')")
        connection.cursor().execute("INSERT INTO people_interactions (person_id,method,note,deleted_at) VALUES (5,'call','Deleted',NOW())")
    academy = get_contact_feed(workspace_id=workspace_id, search='Academy')[0]
    assert [person['name'] for person in academy['people']] == ['Ann']
    assert get_contact_feed(workspace_id=workspace_id, search='Planned') == []
    with db() as connection:
        connection.cursor().execute('UPDATE contacts SET deleted_at=NOW() WHERE id=1')
    ann = get_contact_feed(workspace_id=workspace_id, search='Ann')[0]
    assert ann['kind'] == 'person' and ann['company'] is None and ann['people'] == []


def test_all_linked_people_stay_in_their_group_across_page_boundaries(mixed_contacts):
    workspace_id, _ = mixed_contacts
    with db() as connection:
        connection.cursor().execute("INSERT INTO people (id,name,contact_id,workspace_id) "
                                    "SELECT 10+sequence,'Colleague '||sequence,1,%s FROM generate_series(1,60) sequence", (workspace_id,))
        connection.cursor().execute("INSERT INTO people_interactions (person_id,occurred_at,method,note) "
                                    "SELECT 10+sequence,'2026-10-05T22:30:00Z'::timestamptz,'call','Contact' "
                                    "FROM generate_series(1,60) sequence")
    contacts = get_contact_feed(workspace_id=workspace_id)
    assert len(contacts) == 3
    assert contacts[0]['name'] == 'Academy' and contacts[0]['last_contact'] == '2026-10-06'
    assert len(contacts[0]['people']) == 61
    assert contacts[0]['last_contact_id'] == 70
    assert get_contact_feed(workspace_id=workspace_id, search='Colleague 60')[0]['name'] == 'Academy'
    assert get_contact_feed(workspace_id=workspace_id, page=2) == []


def test_foreign_workspace_person_cannot_enter_business_group_or_search(mixed_contacts):
    workspace_id, other_workspace = mixed_contacts
    with db() as connection:
        connection.cursor().execute("INSERT INTO people (id,name,contact_id,workspace_id) "
                                    "VALUES (5,'Foreign colleague',1,%s)", (other_workspace,))
        connection.cursor().execute("INSERT INTO people_interactions (person_id,occurred_at,method,note) "
                                    "VALUES (5,'2026-10-06T10:00:00Z','call','Contact')")
    academy = get_contact_feed(workspace_id=workspace_id, search='Academy')[0]
    assert academy['last_contact'] == '2026-10-04'
    assert [person['name'] for person in academy['people']] == ['Ann']
    assert get_contact_feed(workspace_id=workspace_id, search='Foreign') == []
    foreign = get_contact_feed(workspace_id=other_workspace, search='Foreign')[0]
    assert foreign['kind'] == 'person' and foreign['company'] is None


def test_business_stage_filter_keeps_people_with_different_stages(mixed_contacts):
    workspace_id, _ = mixed_contacts
    with db() as connection:
        set_person_stage(connection.cursor(), 1, "customer")
    academy = get_contact_feed(workspace_id=workspace_id, stage='candidate')[0]
    assert academy['name'] == 'Academy'
    assert academy['people'][0]['pipeline_stage'] == 'customer'
    assert get_contact_feed(workspace_id=workspace_id, stage='customer') == []
