"""List filtering and sorting are separate forms that preserve each other's state."""
from html.parser import HTMLParser
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from gcrm.api.auth import require_login
from gcrm.api.main import app


class ListForms(HTMLParser):
    def __init__(self, markup):
        super().__init__()
        self.forms = {}
        self.links = {}
        self.current = None
        self.select = None
        self.feed(markup)

    def handle_starttag(self, tag, attributes):
        attributes = dict(attributes)
        if tag == 'a' and attributes.get('id'):
            self.links[attributes['id']] = attributes.get('href')
        if tag == 'form':
            self.current = self.forms.setdefault(attributes.get('id'), {'fields': {}, 'visible': set()})
        if self.current is None:
            return
        name = attributes.get('name')
        if tag == 'input' and name:
            self.current['fields'][name] = attributes.get('value', '')
            if attributes.get('type') != 'hidden':
                self.current['visible'].add(name)
        if tag == 'select':
            self.select = name
            self.current['visible'].add(name)
        if tag == 'option' and self.select:
            fields = self.current['fields']
            if self.select not in fields or 'selected' in attributes:
                fields[self.select] = attributes.get('value', '')

    def handle_endtag(self, tag):
        if tag == 'select':
            self.select = None
        if tag == 'form':
            self.current = None


@pytest.fixture
def list_browser():
    app.dependency_overrides[require_login] = lambda: 'admin'
    with patch('gcrm.api.routers.people.get_people', return_value=[]), \
         patch('gcrm.api.routers.people.get_person_cities', return_value=[]), \
         patch('gcrm.api.routers.organizations._fetch_organizations_page', return_value=([], {}, {}, [], 0)), \
         patch('gcrm.api.routers.contact_feed.get_contact_feed', return_value=[]), \
         patch('gcrm.api.routers.contact_feed.safe_contact_counts', return_value=None):
        yield TestClient(app)
    app.dependency_overrides.pop(require_login, None)


@pytest.mark.parametrize('path', ['/contact-feed/', '/organizations/', '/people/'])
@pytest.mark.parametrize('language', ['en', 'de'])
def test_separate_forms_preserve_applied_settings(list_browser, path, language):
    page = list_browser.get(path, params={'q': 'Ann', 'stage': 'suspect', 'offer': 'consulting',
                                         'sort': 'city', 'dir': 'asc', 'lang': language})
    assert page.status_code == 200
    forms = ListForms(page.text).forms
    filtering, sorting = forms['list-filter-form'], forms['list-sort-form']
    assert 'sort' not in filtering['visible'] and 'dir' not in filtering['visible']
    assert sorting['visible'] == {'sort', 'dir'}
    assert filtering['fields']['sort'] == 'city' and filtering['fields']['dir'] == 'asc'
    assert sorting['fields']['q'] == 'Ann' and sorting['fields']['stage'] == 'suspect'
    assert sorting['fields']['offer'] == 'consulting'
    sorting['fields'].update(sort='name', dir='desc')
    after_sort = list_browser.get(path, params=sorting['fields'])
    updated = ListForms(after_sort.text).forms
    assert updated['list-filter-form']['fields']['q'] == 'Ann'
    filtering = updated['list-filter-form']['fields']
    filtering.update(q='Bob', stage='prospect')
    after_filter = ListForms(list_browser.get(path, params=filtering).text).forms
    assert after_filter['list-sort-form']['fields']['sort'] == 'name'
    assert after_filter['list-sort-form']['fields']['dir'] == 'desc'


@pytest.mark.parametrize('path', ['/contact-feed/', '/organizations/', '/people/'])
def test_resets_only_change_their_own_settings(list_browser, path):
    parameters = {'q': 'Ann', 'stage': 'suspect', 'offer': 'consulting', 'sort': 'city', 'dir': 'asc'}
    page = ListForms(list_browser.get(path, params=parameters).text)
    reset_filter = ListForms(list_browser.get(page.links['reset-filters']).text).forms
    assert reset_filter['list-sort-form']['fields']['q'] == ''
    assert reset_filter['list-sort-form']['fields']['stage'] == ''
    assert reset_filter['list-sort-form']['fields']['offer'] == 'all'
    assert reset_filter['list-sort-form']['fields']['sort'] == 'city'
    assert reset_filter['list-sort-form']['fields']['dir'] == 'asc'
    page = ListForms(list_browser.get(path, params=parameters).text)
    reset_sort = ListForms(list_browser.get(page.links['reset-sort']).text).forms
    fields = reset_sort['list-sort-form']['fields']
    assert fields['q'] == 'Ann' and fields['stage'] == 'suspect' and fields['offer'] == 'consulting'
    assert fields['sort'] == ('last_contact' if path == '/contact-feed/' else 'created_at')
    assert fields['dir'] == 'desc'
