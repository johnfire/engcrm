"""Contact-feed validation, route wiring, tenancy and saved web filters."""
from unittest.mock import patch

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from gcrm.api.auth import require_login
from gcrm.api.jwt_auth import create_token
from gcrm.api.main import app
from gcrm.api.routers.contact_feed import feed_page_link, remember_feed_filters
from gcrm.organization_state import PIPELINE_STAGES
from gcrm.tools.db_contact_feed import feed_predicates, validate_feed_filters

AUTH = {"Authorization": f"Bearer {create_token('spectator')}"}
CONTACT = {"id": 7, "kind": "person", "name": "Ann", "description": "Coordinator", "company": "Academy",
           "city": "Ulm", "email": "ann@academy.test", "phone": None,
           "pipeline_stage": "candidate", "created_at": "2026-10-06T12:00:00+00:00", "last_contact": "2026-10-04"}


@pytest.mark.parametrize("stage", ["", "none", *PIPELINE_STAGES])
def test_valid_contact_filters(stage):
    validate_feed_filters("person", stage, "newest")


@pytest.mark.parametrize("kind,stage,sort", [("alien", "", "newest"), ("", "invalid", "name"), ("", "", "sql")])
def test_invalid_filters_are_rejected(kind, stage, sort):
    with pytest.raises(ValueError):
        validate_feed_filters(kind, stage, sort)


def test_search_parameters_are_literal_and_workspace_and_type_are_bound():
    predicate, parameters = feed_predicates("100% a_b!", "person", "suspect", 3)
    assert "workspace_id=%s" in predicate and "kind=%s" in predicate
    assert "100%" not in predicate
    assert "%s = ANY(deal_stages)" in predicate  # one of the shown deals is at that stage
    assert parameters[:3] == [3, "person", "suspect"]
    assert parameters[3:10] == ["%100!%%"] * 7
    assert parameters[10:] == ["%a!_b!!%"] * 7
    assert feed_predicates("", "", "none", None) == ("last_contact IS NOT NULL AND cardinality(deal_stages) = 0", [])
    assert feed_predicates("", "", "", None) == ("last_contact IS NOT NULL", [])
    assert feed_predicates("", "", "", None, only_pitched=True) == (
        "last_contact IS NOT NULL AND cardinality(deal_stages) > 0", [])


def test_web_filters_are_remembered_and_clear_resets_them():
    request = Request({"type": "http", "session": {}})
    selected = remember_feed_filters(request, q="Ann", kind="person", stage="suspect", sort="name")
    assert remember_feed_filters(request, q=None, kind=None, stage=None, sort=None) == selected
    cleared = remember_feed_filters(request, q="", kind="", stage="", sort="newest")
    assert cleared == {"search": "", "kind": "", "stage": "", "sort": "last_contact"}
    assert "q=Ann" in feed_page_link(2, selected) and "page=2" in feed_page_link(2, selected)


def test_mobile_contacts_pass_filters_and_signed_in_workspace_to_query():
    with patch("gcrm.api.routers.contact_feed.get_contact_feed", return_value=[CONTACT]) as fetch, \
         patch("gcrm.api.routers.contact_feed._personal_identity", return_value=(9, 3)):
        response = TestClient(app).get("/api/contact-feed?search=Ann&kind=person&stage=candidate&sort=name&page=2", headers=AUTH)
    assert response.status_code == 200 and response.json() == [CONTACT]
    # no offer asked for: the Consulting view, nobody hidden — what the installed app expects
    fetch.assert_called_once_with(search="Ann", kind="person", stage="candidate", sort="name", page=2, workspace_id=3,
                                  offer="consulting", only_pitched=False)


@pytest.mark.parametrize("parameters", ["kind=alien", "stage=bogus", "sort=bogus", "page=0", "search=" + "x" * 101])
def test_mobile_invalid_filters_never_query_database(parameters):
    with patch("gcrm.api.routers.contact_feed.get_contact_feed") as fetch:
        response = TestClient(app).get("/api/contact-feed?" + parameters, headers=AUTH)
    assert response.status_code in (400, 422)
    fetch.assert_not_called()


def test_both_contact_views_require_sign_in():
    browser = TestClient(app)
    assert browser.get("/api/contact-feed").status_code in (401, 403)
    assert browser.get("/contact-feed/", follow_redirects=False).status_code in (303, 307)


def test_web_links_labels_pagination_and_filter_persistence():
    app.dependency_overrides[require_login] = lambda: "admin"
    try:
        with patch("gcrm.api.routers.contact_feed.get_contact_feed", return_value=[CONTACT] * 51) as fetch:
            browser = TestClient(app)
            response = browser.get("/contact-feed/?q=Ann&kind=person&stage=candidate&sort=name&lang=en")
            assert response.status_code == 200
            assert 'href="/people/7"' in response.text
            assert "Coordinator" in response.text and "Academy" in response.text
            assert 'page=2' in response.text and 'href="/contact-feed/"' in response.text
            assert 'value="person" selected' in response.text
            browser.get("/contact-feed/")
            assert fetch.call_args.kwargs["search"] == "Ann"
            assert fetch.call_args.kwargs["kind"] == "person"
            assert fetch.call_args.kwargs["extra_row"] is True
            german = browser.get("/contact-feed/?lang=de").text
            assert "Kontakte" in german and "Organisation" in german
    finally:
        app.dependency_overrides.pop(require_login, None)


COUNTS = {"month": {"people": 3, "organizations": 1}, "since_start": {"people": 12, "organizations": 9},
          "month_start": "2026-10-01", "business_start": "2026-10-01"}


def test_mobile_counts_use_the_signed_in_workspace():
    with patch("gcrm.api.routers.contact_feed.get_contact_counts", return_value=COUNTS) as counts, \
         patch("gcrm.api.routers.contact_feed._personal_identity", return_value=(9, 3)):
        response = TestClient(app).get("/api/contact-feed/counts", headers=AUTH)
    assert response.status_code == 200 and response.json() == COUNTS
    counts.assert_called_once_with(3, offer=None)


def test_web_page_shows_month_and_since_start_counts_in_both_languages():
    app.dependency_overrides[require_login] = lambda: "admin"
    try:
        with patch("gcrm.api.routers.contact_feed.get_contact_feed", return_value=[CONTACT]), \
             patch("gcrm.api.routers.contact_feed.get_contact_counts", return_value=COUNTS):
            english = TestClient(app).get("/contact-feed/?lang=en").text
            german = TestClient(app).get("/contact-feed/?lang=de").text
        assert "This month" in english and "3 people" in english and "1 organization" in english
        assert "All time (since 2026-10-01)" in english and "12 people" in english and "9 organizations" in english
        assert "Diesen Monat" in german and "3 Personen" in german and "9 Organisationen" in german
    finally:
        app.dependency_overrides.pop(require_login, None)


def test_web_contact_list_still_loads_when_counts_fail():
    app.dependency_overrides[require_login] = lambda: "admin"
    try:
        with patch("gcrm.api.routers.contact_feed.get_contact_feed", return_value=[CONTACT]), \
             patch("gcrm.api.routers.contact_feed.get_contact_counts", side_effect=RuntimeError("db")):
            response = TestClient(app).get("/contact-feed/?lang=en")
        assert response.status_code == 200 and 'href="/people/7"' in response.text
        assert "This month" not in response.text
    finally:
        app.dependency_overrides.pop(require_login, None)
