"""Mixed chronology and pagination against actual PostgreSQL."""
import pytest

from gcrm.db.connection import db
from gcrm.tools.db_contact_feed import get_contact_feed

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
        cursor.execute("INSERT INTO contacts (id,name,city,workspace_id,pipeline_stage,created_at) VALUES "
                       "(1,'Academy','Augsburg',%s,'candidate','2026-10-05T10:00:00Z'), "
                       "(2,'Other company','Ulm',%s,'suspect','2026-10-06T10:00:00Z'), "
                       "(3,'Hidden organization','Ulm',%s,'candidate','2026-10-07T10:00:00Z')", (workspace_id, workspace_id, other_workspace))
        cursor.execute("INSERT INTO people (id,name,title,email,contact_id,workspace_id,pipeline_stage,created_at) VALUES "
                       "(1,'Ann','Course coordinator','ann@academy.test',1,%s,'candidate','2026-10-06T10:00:00Z'), "
                       "(2,'No stage',NULL,NULL,NULL,%s,NULL,'2026-10-04T10:00:00Z'), "
                       "(3,'Hidden person',NULL,NULL,3,%s,NULL,'2026-10-07T10:00:00Z')", (workspace_id, workspace_id, other_workspace))
        cursor.execute("INSERT INTO people (id,name,contact_id,workspace_id,created_at,deleted_at) "
                       "VALUES (4,'Deleted person',1,%s,NOW(),NOW())", (workspace_id,))
    return workspace_id, other_workspace


def test_types_share_one_stable_order_and_keep_colliding_ids(mixed_contacts):
    workspace_id, _ = mixed_contacts
    contacts = get_contact_feed(workspace_id=workspace_id)
    assert [(contact['kind'], contact['id']) for contact in contacts] == [
        ('organization', 2), ('person', 1), ('organization', 1), ('person', 2),
    ]
    assert contacts[1]['company'] == 'Academy' and contacts[1]['city'] == 'Augsburg'
    assert contacts[1]['description'] == 'Course coordinator'
    assert get_contact_feed(workspace_id=workspace_id) == contacts
    assert len(get_contact_feed(workspace_id=workspace_id, kind='person')) == 2
    assert len(get_contact_feed(workspace_id=workspace_id, stage='candidate')) == 2
    assert get_contact_feed(workspace_id=workspace_id, stage='none')[0]['name'] == 'No stage'
    assert get_contact_feed(workspace_id=workspace_id, search='Ann Academy')[0]['name'] == 'Ann'
    assert get_contact_feed(workspace_id=workspace_id, search='ann@academy.test')[0]['kind'] == 'person'
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
    first = get_contact_feed(workspace_id=workspace_id)
    second = get_contact_feed(workspace_id=workspace_id, page=2)
    assert len(first) == 50 and len(second) == 14
    identities = [(contact['kind'], contact['id']) for contact in first + second]
    assert len(set(identities)) == 64
    assert len(get_contact_feed(workspace_id=workspace_id, extra_row=True)) == 51
    assert get_contact_feed(workspace_id=workspace_id, page=3) == []
