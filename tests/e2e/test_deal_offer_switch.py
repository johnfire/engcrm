"""Select an existing deal's offer on the website, preserving its identity and state."""
from datetime import date

import pytest
from fastapi.testclient import TestClient

from gcrm.api.main import app
from gcrm.api.security import hash_password
from gcrm.audit_context import audit_scope
from gcrm.db.connection import db
from gcrm.tools.db_offers import list_offers
from gcrm.tools.db_organizations import save_organization
from gcrm.tools.db_users import create_user
from gcrm.tools.deal_records import get_deals, set_deal_next_step

pytestmark = pytest.mark.e2e


@pytest.fixture
def offered_company(clean_database, monkeypatch):
    monkeypatch.setattr('gcrm.tools.db_organizations.geocode', lambda *args: None)
    password = 'offer-switch-test-password'
    user_id = create_user('offer-switch@example.test', hash_password(password), 'admin')
    with audit_scope('test-fixture', 'user', 'fixture'):
        company = save_organization('BIB example', '', source='test_fixture', pipeline_stage='nibble', status='contacted')
        [deal] = get_deals('organization', company)
        set_deal_next_step(deal['id'], 'Follow up', date(2026, 11, 20))
    offers = {offer['slug']: offer['id'] for offer in list_offers(None)}
    browser = TestClient(app)
    browser.post('/login', data={'email': 'offer-switch@example.test', 'password': password})
    token = browser.post('/api/auth/token', json={'email': 'offer-switch@example.test', 'password': password}).json()['token']
    return browser, company, deal['id'], offers, {'Authorization': 'Bearer ' + token}, user_id


def test_offer_selector_switches_the_existing_card_and_keeps_nibble(offered_company):
    browser, company, deal_id, offers, _, _ = offered_company
    before = browser.get(f'/organizations/{company}')
    assert f'action="/deals/{deal_id}/offer"' in before.text
    assert f'id="deal-{deal_id}-offer"' in before.text
    assert f'value="{offers["training"]}">Training</option>' in before.text
    changed = browser.post(f'/deals/{deal_id}/offer', data={
        'offer_id': offers['training'], 'next': f'/organizations/{company}',
    }, headers={'X-Request-ID': 'switch-existing-offer'}, follow_redirects=False)
    assert changed.status_code == 303
    assert changed.headers['location'] == f'/organizations/{company}'
    [stored] = get_deals('organization', company)
    assert stored['id'] == deal_id and stored['offer_slug'] == 'training'
    assert stored['pipeline_stage'] == 'nibble' and stored['status'] == 'contacted'
    assert stored['next_step'] == 'Follow up' and stored['next_step_date'] == '2026-11-20'
    page = browser.get(changed.headers['location'])
    assert '<h3>Training' in page.text and '>Nibble</option>' in page.text
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT actor,correlation_id FROM audit_log WHERE action='deal.offer_changed' AND target=%s", (f'deal:{deal_id}',))
        audit = cursor.fetchone()
    assert audit['actor'] == 'offer-switch@example.test' and audit['correlation_id'] == 'switch-existing-offer'


def test_api_can_switch_back_and_refuses_duplicate_targets(offered_company):
    browser, company, deal_id, offers, headers, _ = offered_company
    changed = browser.patch(f'/api/deals/{deal_id}/offer', headers=headers, json={'offer_id': offers['training']})
    assert changed.status_code == 200 and changed.json()['id'] == deal_id
    restored = browser.patch(f'/api/deals/{deal_id}/offer', headers=headers, json={'offer_id': offers['consulting']})
    assert restored.status_code == 200 and restored.json()['offer_slug'] == 'consulting'
    additional = browser.post('/api/deals', headers=headers, json={
        'owner': 'organization', 'owner_id': company, 'offer_id': offers['training'],
    })
    assert additional.status_code == 201
    refused = browser.patch(f'/api/deals/{deal_id}/offer', headers=headers, json={'offer_id': offers['training']})
    assert refused.status_code == 409
    assert len(get_deals('organization', company)) == 2


def test_nibble_is_visible_in_statistics_and_stage_filters(offered_company):
    browser, company, _, _, _, _ = offered_company
    people = browser.get('/organizations/?stage=nibble&offer=all')
    assert f'href="/organizations/{company}"' in people.text
    statistics = browser.get('/statistics')
    assert statistics.status_code == 200 and '>Nibble</td>' in statistics.text
