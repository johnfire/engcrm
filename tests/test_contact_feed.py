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
    assert feed_predicates("", "", "none", None) == (
        "(last_contact IS NOT NULL OR contacted) AND cardinality(deal_stages) = 0", [])
    # Without a stage filter nobody contacted is hidden: dated, or contacted by status alone.
    assert feed_predicates("", "", "", None) == ("(last_contact IS NOT NULL OR contacted)", [])


def test_web_filters_are_remembered_and_clear_resets_them():
    request = Request({"type": "http", "session": {}})
    selected = remember_feed_filters(request, q="Ann", kind="person", stage="suspect", sort="name")
    assert remember_feed_filters(request, q=None, kind=None, stage=None, sort=None) == selected
    cleared = remember_feed_filters(request, q="", kind="", stage="", sort="newest")
    assert cleared == {"search": "", "kind": "", "stage": "", "sort": "last_contact", "dir": ""}
    assert "q=Ann" in feed_page_link(2, selected) and "page=2" in feed_page_link(2, selected)


def test_mobile_contacts_pass_filters_and_signed_in_workspace_to_query():
    with patch("gcrm.api.routers.contact_feed.get_contact_feed", return_value=[CONTACT]) as fetch, \
         patch("gcrm.api.routers.contact_feed._personal_identity", return_value=(9, 3)):
        response = TestClient(app).get("/api/contact-feed?search=Ann&kind=person&stage=candidate&sort=name&page=2", headers=AUTH)
    assert response.status_code == 200 and response.json() == [CONTACT]
    # no offer asked for: the Consulting view, nobody hidden — what the installed app expects
    fetch.assert_called_once_with(search="Ann", kind="person", stage="candidate", sort="name", page=2, workspace_id=3,
                                  offer="consulting")


def test_contacts_outside_the_pipeline_are_neither_hidden_nor_moved():
    from gcrm.tools import db_contact_feed

    with patch.object(db_contact_feed, "db") as database:
        cursor = database.return_value.__enter__.return_value.cursor.return_value
        cursor.fetchall.return_value = []
        db_contact_feed.get_contact_feed(workspace_id=3, offer="training", sort="name")
    sql = cursor.execute.call_args.args[0]
    assert "cardinality(deal_stages) > 0" not in sql
    # The stage never moves a row: the requested sort is the whole order.
    assert "ORDER BY lower(name) ASC NULLS LAST, kind, id LIMIT" in sql
    assert "not_in_pipeline" not in sql.split("ORDER BY")[-1]


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
        assert "All time (since 01.10.2026)" in english and "12 people" in english and "9 organizations" in english
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


def test_web_list_shows_my_ratings_instead_of_email_or_phone():
    rated = {**CONTACT, "priority": 2, "long_term_value": 3, "short_term_value": 0}
    app.dependency_overrides[require_login] = lambda: "admin"
    try:
        with patch("gcrm.api.routers.contact_feed.get_contact_feed", return_value=[rated]) as fetch:
            response = TestClient(app).get("/contact-feed/?lang=en")
    finally:
        app.dependency_overrides.pop(require_login, None)
    assert response.status_code == 200
    header = response.text.split("<thead>")[1].split("</thead>")[0]
    assert ">Priority<" in header and ">LT<" in header and ">ST<" in header
    assert "Email / phone" not in header
    body = response.text.split("<tbody>")[1]
    assert "ann@academy.test" not in body
    assert ">P2<" in body and 'title="High">H<' in body and 'title="Zero">0<' in body
    assert "user_id" in fetch.call_args.kwargs


@pytest.mark.parametrize("sort,column,direction", [
    ("priority", "rating.priority", "ASC"),
    ("long_term_value", "rating.long_term_value", "DESC"),
    ("short_term_value", "rating.short_term_value", "DESC"),
])
def test_feed_sorts_by_my_ratings_best_first(sort, column, direction):
    from unittest.mock import MagicMock

    from gcrm.tools.db_contact_feed import get_contact_feed

    connection = MagicMock()
    connection.cursor.return_value.fetchall.return_value = []
    with patch("gcrm.tools.db_contact_feed.db") as database:
        database.return_value.__enter__.return_value = connection
        get_contact_feed(sort=sort, user_id=9)
    query, parameters = connection.cursor.return_value.execute.call_args.args
    # Best rating first, whatever the pipeline stage.
    assert f"ORDER BY {column} {direction} NULLS LAST" in query
    assert parameters[:2] == [9, 9]  # the two rating tables, read for this user only


def test_web_list_shows_next_contact_with_overdue_marked_and_step_on_hover():
    overdue = {**CONTACT, "id": 1, "next_contact": "2020-01-31", "next_contact_step": "Invite to coffee"}
    upcoming = {**CONTACT, "id": 2, "next_contact": "2099-12-31", "next_contact_step": "Send portfolio"}
    undated = {**CONTACT, "id": 3, "next_contact": None, "next_contact_step": None}
    app.dependency_overrides[require_login] = lambda: "admin"
    try:
        with patch("gcrm.api.routers.contact_feed.get_contact_feed", return_value=[overdue, upcoming, undated]):
            english = TestClient(app).get("/contact-feed/?lang=en")
            german = TestClient(app).get("/contact-feed/?lang=de")
    finally:
        app.dependency_overrides.pop(require_login, None)
    assert english.status_code == 200
    assert ">Next contact<" in english.text.split("<thead>")[1].split("</thead>")[0]
    assert ">Nächster Kontakt<" in german.text.split("<thead>")[1].split("</thead>")[0]
    rows = english.text.split("<tbody>")[1].split("</tbody>")[0].split("<tr>")[1:]
    assert 'next-step__due next-step__due--overdue" title="Invite to coffee">31.01.2020' in rows[0]
    assert '<span class="sr-only"> · overdue</span>' in rows[0]
    assert 'next-step__due" title="Send portfolio">31.12.2099' in rows[1] and "overdue" not in rows[1]
    assert "next-step__due" not in rows[2]


def test_feed_sorts_by_next_contact_soonest_first_blanks_last():
    from unittest.mock import MagicMock

    from gcrm.tools.db_contact_feed import get_contact_feed

    connection = MagicMock()
    connection.cursor.return_value.fetchall.return_value = []
    with patch("gcrm.tools.db_contact_feed.db") as database:
        database.return_value.__enter__.return_value = connection
        get_contact_feed(sort="next_contact")
    query = connection.cursor.return_value.execute.call_args.args[0]
    assert "ORDER BY next_contact ASC NULLS LAST, kind, id" in query


def test_contacted_without_a_date_shows_a_dash_not_none():
    undated = {**CONTACT, "kind": "organization", "id": 929, "name": "Mischok GmbH", "last_contact": None,
               "last_contact_kind": "organization", "last_contact_id": 929}
    app.dependency_overrides[require_login] = lambda: "admin"
    try:
        with patch("gcrm.api.routers.contact_feed.get_contact_feed", return_value=[undated]):
            response = TestClient(app).get("/contact-feed/?lang=en")
    finally:
        app.dependency_overrides.pop(require_login, None)
    row = response.text.split("<tbody>")[1].split("</tbody>")[0]
    assert "None" not in row
    assert 'title="Contacted, date not recorded">—</span><span class="sr-only"> Contacted, date not recorded</span>' in row
