"""Add contacts, browse the combined list, and open both kinds on web/mobile."""
import pytest
from fastapi.testclient import TestClient

from gcrm.api.main import app
from gcrm.api.security import hash_password
from gcrm.tools.db_users import create_user

pytestmark = pytest.mark.e2e


def test_new_person_and_company_appear_together_and_open_their_own_details(clean_database, monkeypatch):
    monkeypatch.setattr('gcrm.tools.db_people.geocode', lambda city, country: None)
    monkeypatch.setattr('gcrm.tools.db_organizations.geocode', lambda city, country: None)
    password = 'combined-contacts-password'
    create_user('contacts@example.test', hash_password(password), 'admin')
    browser = TestClient(app)
    token = browser.post('/api/auth/token', json={'email': 'contacts@example.test', 'password': password}).json()['token']
    headers = {'Authorization': f'Bearer {token}'}
    organization = browser.post('/api/contacts', headers=headers, json={'name': 'Academy', 'city': 'Augsburg'})
    assert organization.status_code == 200
    organization_id = organization.json()['id']
    person = browser.post('/api/people', headers=headers, json={
        'name': 'Ann Example', 'title': 'Coordinator', 'contact_id': organization_id,
        'email': 'ann@academy.test', 'pipeline_stage': 'candidate',
    })
    assert person.status_code == 200
    person_id = person.json()['id']
    contacts = browser.get('/api/contact-feed', headers=headers).json()
    assert [(contact['kind'], contact['id']) for contact in contacts] == [('person', person_id), ('organization', organization_id)]
    assert browser.get(f'/api/people/{person_id}', headers=headers).json()['name'] == 'Ann Example'
    assert browser.get(f'/api/contacts/{organization_id}', headers=headers).json()['name'] == 'Academy'
    assert browser.post('/login', data={'email': 'contacts@example.test', 'password': password}, follow_redirects=False).status_code == 303
    feed = browser.get('/contact-feed/?q=Academy').text
    assert feed.index(f'href="/people/{person_id}"') < feed.index(f'href="/organizations/{organization_id}"')
    assert browser.get(f'/people/{person_id}').status_code == 200
    assert browser.get(f'/organizations/{organization_id}').status_code == 200
    returned = browser.get('/contact-feed/').text
    assert 'value="Academy"' in returned
    assert browser.get('/api/contact-feed?kind=person&stage=candidate', headers=headers).json()[0]['id'] == person_id
