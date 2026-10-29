"""Add contacts, browse the combined list, and open both kinds on web/mobile."""
import pytest
from fastapi.testclient import TestClient

from gcrm.api.main import app
from gcrm.api.security import hash_password
from gcrm.tools.db_users import create_user

pytestmark = pytest.mark.e2e


@pytest.fixture
def linked_contacts(clean_database, monkeypatch):
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
    return browser, headers, organization_id, person_id, password


def test_new_person_and_company_appear_together_and_open_their_own_details(linked_contacts):
    browser, headers, organization_id, person_id, password = linked_contacts
    assert browser.get('/api/contact-feed', headers=headers).json() == []
    for kind, contact_id, day in [('organization', organization_id, '2026-10-03'), ('person', person_id, '2026-10-04')]:
        assert browser.patch(f'/api/contact-feed/{kind}/{contact_id}/date', headers=headers,
                             json={'contact_date': day}).status_code == 200
    contacts = browser.get('/api/contact-feed', headers=headers).json()
    assert [(contact['kind'], contact['id']) for contact in contacts] == [('organization', organization_id)]
    assert contacts[0]['people'][0]['id'] == person_id
    assert contacts[0]['last_contact'] == '2026-10-04'
    assert contacts[0]['last_contact_kind'] == 'person'
    assert contacts[0]['last_contact_id'] == person_id
    assert browser.get(f'/api/people/{person_id}', headers=headers).json()['name'] == 'Ann Example'
    assert browser.get(f'/api/contacts/{organization_id}', headers=headers).json()['name'] == 'Academy'
    assert browser.post('/login', data={'email': 'contacts@example.test', 'password': password}, follow_redirects=False).status_code == 303
    feed = browser.get('/contact-feed/?q=Academy').text
    assert feed.index(f'href="/organizations/{organization_id}"') < feed.index(f'href="/people/{person_id}"')
    assert 'Contacted people (1)' in feed and 'With Ann Example' in feed
    assert f'href="/contact-feed/person/{person_id}/date"' in feed
    assert browser.get(f'/people/{person_id}').status_code == 200
    assert browser.get(f'/organizations/{organization_id}').status_code == 200
    returned = browser.get('/contact-feed/').text
    assert 'value="Academy"' in returned
    assert browser.get('/api/contact-feed?kind=person&stage=candidate', headers=headers).json() == []
    assert browser.get('/api/contact-feed?search=Ann', headers=headers).json()[0]['id'] == organization_id
    latest = browser.get(f'/api/contact-feed/person/{person_id}/date', headers=headers).json()
    assert browser.patch(f'/api/contact-feed/person/{person_id}/date', headers=headers, json={
        'contact_date': '2026-10-02', 'interaction_id': latest['interaction_id'], 'previous_date': latest['contact_date'],
    }).status_code == 200
    corrected = browser.get('/api/contact-feed', headers=headers).json()[0]
    assert corrected['last_contact'] == '2026-10-03' and corrected['last_contact_kind'] == 'organization'
    assert corrected['people'][0]['last_contact'] == '2026-10-02'
    assert browser.get(f'/api/contact-feed/organization/{organization_id}/date', headers=headers).json()['contact_date'] == '2026-10-03'


@pytest.mark.parametrize('path,first_name,last_name', [
    ('/contact-feed/', 'Academy', 'Zulu'),
    ('/organizations/', 'Academy', 'Zulu'),
    ('/people/', 'Ann Example', 'Zara Example'),
])
def test_sort_controls_order_real_records_in_both_directions(linked_contacts, path, first_name, last_name):
    from gcrm.db.connection import db
    from gcrm.tools.db_deals import set_organization_deal

    browser, headers, organization_id, person_id, password = linked_contacts
    organization = browser.post('/api/contacts', headers=headers, json={'name': 'Zulu', 'city': 'Berlin'})
    other_id = organization.json()['id']
    person = browser.post('/api/people', headers=headers, json={
        'name': 'Zara Example', 'city': 'Berlin', 'pipeline_stage': 'suspect',
        'contact_id': other_id,
    })
    other_person_id = person.json()['id']
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("UPDATE people SET city='Augsburg' WHERE id=%s", (person_id,))
        set_organization_deal(cursor, organization_id, stage='candidate')
        set_organization_deal(cursor, other_id, stage='suspect')
    for kind, contact_id, day in [('organization', organization_id, '2026-10-03'),
                                 ('organization', other_id, '2026-10-05'),
                                 ('person', person_id, '2026-10-03'),
                                 ('person', other_person_id, '2026-10-05')]:
        response = browser.patch(f'/api/contact-feed/{kind}/{contact_id}/date', headers=headers,
                                 json={'contact_date': day})
        assert response.status_code == 200
    browser.post('/login', data={'email': 'contacts@example.test', 'password': password})
    for sort in ('name', 'city', 'pipeline_stage', 'last_contact'):
        for direction in ('asc', 'desc'):
            response = browser.get(path, params={'sort': sort, 'dir': direction, 'offer': 'all'})
            assert response.status_code == 200
            assert f'value="{sort}" selected' in response.text
            first_position = response.text.index(f'>{first_name}</a>')
            last_position = response.text.index(f'>{last_name}</a>')
            first_before_last = direction == 'asc'
            if sort == 'pipeline_stage':
                first_before_last = not first_before_last  # Suspect ranks before Candidate ascending.
            assert (first_position < last_position) == first_before_last, (path, sort, direction)


@pytest.mark.parametrize('path,query', [('/contact-feed/', 'Academy'),
                                       ('/organizations/', 'Academy'), ('/people/', 'Ann')])
def test_filter_and_sort_forms_work_independently_with_real_records(linked_contacts, path, query):
    from tests.test_list_control_forms import ListForms

    browser, headers, organization_id, person_id, password = linked_contacts
    browser.patch(f'/api/contact-feed/person/{person_id}/date', headers=headers,
                  json={'contact_date': '2026-10-29'})
    browser.post('/login', data={'email': 'contacts@example.test', 'password': password})
    page = browser.get(path, params={'stage': 'candidate', 'offer': 'consulting', 'sort': 'name', 'dir': 'asc'})
    assert page.status_code == 200
    forms = ListForms(page.text).forms
    sorting = forms['list-sort-form']['fields']
    sorting.update(sort='city', dir='desc')
    sorted_page = browser.get(path, params=sorting)
    assert sorted_page.status_code == 200
    filtering = ListForms(sorted_page.text).forms['list-filter-form']['fields']
    filtering['q'] = query
    filtered_page = browser.get(path, params=filtering)
    assert filtered_page.status_code == 200 and query in filtered_page.text
    controls = ListForms(filtered_page.text)
    assert controls.forms['list-sort-form']['fields']['sort'] == 'city'
    reset_sort = browser.get(controls.links['reset-sort'])
    assert reset_sort.status_code == 200
    reset_controls = ListForms(reset_sort.text)
    assert reset_controls.forms['list-filter-form']['fields']['q'] == query
    assert reset_controls.forms['list-filter-form']['fields']['stage'] == 'candidate'
    reset_filter = browser.get(reset_controls.links['reset-filters'])
    assert reset_filter.status_code == 200
    final_sorting = ListForms(reset_filter.text).forms['list-sort-form']['fields']
    assert final_sorting['q'] == '' and final_sorting['stage'] == ''
    assert final_sorting['dir'] == 'desc'
