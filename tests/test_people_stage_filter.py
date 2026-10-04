"""People stage preferences survive list/detail navigation and explicit resets."""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from gcrm.api.auth import require_login
from gcrm.api.main import app
from gcrm.api.routers.people import remember_people_stage
from gcrm.organization_state import PIPELINE_STAGES

PERSON = {
    "id": 3, "name": "Anna", "distance_km": None, "created_at": "2026-10-04",
    "last_contact": None, "value_rating": None, "company_personal_priority": None,
    "company_opportunity_score": None, "pipeline_stage": "suspect",
}


@pytest.mark.parametrize("stage", [*PIPELINE_STAGES, "none", ""])
def test_explicit_stage_replaces_saved_selection(stage):
    request = Request({"type": "http", "session": {"people_stage": "suspect"}})
    assert remember_people_stage(request, stage) == stage
    assert request.session["people_stage"] == stage


@pytest.mark.parametrize("session, expected", [
    ({}, ""), ({"people_stage": "suspect"}, "suspect"),
    ({"people_stage": "bogus"}, ""),
])
def test_missing_stage_uses_valid_saved_selection(session, expected):
    request = Request({"type": "http", "session": session})
    assert remember_people_stage(request, None) == expected


def test_unknown_explicit_stage_resets_selection():
    request = Request({"type": "http", "session": {"people_stage": "suspect"}})
    assert remember_people_stage(request, "bogus") == ""
    assert request.session["people_stage"] == ""


@pytest.fixture
def people_browser():
    app.dependency_overrides[require_login] = lambda: "admin"
    with (
        TestClient(app) as browser,
        patch("gcrm.api.routers.people.get_people", return_value=[]) as fetch_people,
        patch("gcrm.api.routers.people.get_person_cities", return_value=[]),
    ):
        yield browser, fetch_people
    app.dependency_overrides.pop(require_login, None)


def test_selected_stage_survives_opening_person_and_returning(people_browser):
    browser, fetch_people = people_browser
    assert browser.get("/people/?stage=suspect").status_code == 200
    with (
        patch("gcrm.api.routers.people.get_person", return_value=PERSON),
        patch("gcrm.api.routers.people.get_person_interactions", return_value=[]),
    ):
        assert browser.get("/people/3").status_code == 200
    returned_page = browser.get("/people/")
    assert fetch_people.call_args.kwargs["stage"] == "suspect"
    assert '<option value="suspect" selected>' in returned_page.text
    assert 'href="/people/?stage="' in returned_page.text
    assert browser.get("/people/?sort=name&dir=asc").status_code == 200
    assert fetch_people.call_args.kwargs["stage"] == "suspect"


def test_all_stages_clears_saved_selection(people_browser):
    browser, fetch_people = people_browser
    browser.get("/people/?stage=suspect")
    browser.get("/people/?stage=")
    assert browser.get("/people/").status_code == 200
    assert fetch_people.call_args.kwargs["stage"] == ""


def test_new_browser_starts_with_all_stages(people_browser):
    browser, fetch_people = people_browser
    browser.get("/people/?stage=suspect")
    with TestClient(app) as other_browser:
        assert other_browser.get("/people/").status_code == 200
    assert fetch_people.call_args.kwargs["stage"] == ""


def test_saved_stage_survives_browser_restart_with_same_cookies(people_browser):
    browser, fetch_people = people_browser
    browser.get("/people/?stage=suspect")
    with TestClient(app, cookies=browser.cookies) as reopened_browser:
        assert reopened_browser.get("/people/").status_code == 200
    assert fetch_people.call_args.kwargs["stage"] == "suspect"


@pytest.mark.parametrize("language, full_label, all_label", [
    ("en", "Company priority", "All CP"), ("de", "Firmenpriorität", "Alle CP"),
])
def test_priority_labels_are_compact_and_accessible(people_browser, language, full_label, all_label):
    browser, fetch_people = people_browser
    fetch_people.return_value = [PERSON]
    response = browser.get(f"/people/?lang={language}")
    assert response.status_code == 200
    assert f'aria-label="{full_label}"' in response.text
    assert f'<option value="">{all_label}</option>' in response.text
    assert f'<option value="company_priority" title="{full_label}" >CP</option>' in response.text
    assert '>CP</a></th>' in response.text
