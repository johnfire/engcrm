"""Pipeline stages sort by business meaning on every list, with missing stages last."""
import re

import pytest
from fastapi.testclient import TestClient

from gcrm.api.auth import require_login
from gcrm.api.main import app
from gcrm.db.connection import db
from gcrm.tools.db_deals import set_organization_deal, set_person_stage

pytestmark = pytest.mark.integration
EXPECTED_STAGES = ('customer', 'opportunity', 'prospect', 'suspect', 'candidate', 'not_in_pipeline')


@pytest.fixture
def ranked_contacts(clean_database):
    owners = {}
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug='default'")
        workspace_id = cursor.fetchone()['id']
        for stage in (*EXPECTED_STAGES, None):
            for kind, table in [('organizations', 'contacts'), ('people', 'people')]:
                cursor.execute(f'INSERT INTO {table} (name,workspace_id) VALUES (%s,%s) RETURNING id',
                               (f'Rank {stage or "missing"}', workspace_id))
                owner_id = cursor.fetchone()['id']
                owners[(kind, str(owner_id))] = stage
                if kind == 'organizations':
                    if stage:
                        set_organization_deal(cursor, owner_id, stage=stage)
                    cursor.execute("INSERT INTO interactions (contact_id,interaction_date,method) "
                                   "VALUES (%s,'2026-10-29','phone')", (owner_id,))
                else:
                    if stage:
                        set_person_stage(cursor, owner_id, stage)
                    cursor.execute("INSERT INTO people_interactions (person_id,method,note) "
                                   "VALUES (%s,'call','Rank test')", (owner_id,))
    app.dependency_overrides[require_login] = lambda: 'admin'
    yield TestClient(app), owners
    app.dependency_overrides.pop(require_login, None)


@pytest.mark.parametrize('path', ['/contact-feed/', '/organizations/', '/people/'])
@pytest.mark.parametrize('direction', ['asc', 'desc'])
@pytest.mark.parametrize('offer', ['all', 'consulting'])
def test_business_stage_order_on_each_page(ranked_contacts, path, direction, offer):
    browser, owners = ranked_contacts
    response = browser.get(path, params={'q': 'Rank', 'sort': 'pipeline_stage', 'dir': direction, 'offer': offer})
    assert response.status_code == 200
    links = re.findall(r'href="/(people|organizations)/(\d+)"', response.text)
    shown = [owners[owner] for owner in links if owner in owners]
    stages = EXPECTED_STAGES if direction == 'asc' else EXPECTED_STAGES[::-1]
    repetitions = 2 if path == '/contact-feed/' else 1
    expected = [stage for stage in stages for _ in range(repetitions)]
    # A selected offer deliberately hides contacts without a deal for it.
    if offer == 'all':
        expected += [None] * repetitions
    assert shown == expected
