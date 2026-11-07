"""The Forecast page and its plan forms, through real logins on the real schema."""
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

import gcrm.api.main as main
from gcrm.api.security import hash_password
from gcrm.db.connection import db
from gcrm.tools.db_organizations import save_organization
from gcrm.tools.deal_money import add_deal_sale
from gcrm.tools.deal_records import get_deals
from gcrm.tools.income_plan import add_other_income, get_plan
from gcrm.workspace_context import workspace_scope

pytestmark = pytest.mark.integration
PASSWORD = "a-long-test-password-1"


def _user(workspace, email, role="admin"):
    with db() as connection:
        connection.cursor().execute(
            "INSERT INTO users (email, name, password_hash, role, workspace_id, is_active) VALUES (%s, %s, %s, %s, %s, TRUE)",
            (email, email.split("@")[0], hash_password(PASSWORD), role, workspace))


def _browser(email):
    browser = TestClient(main.app)
    assert browser.post("/login", data={"email": email, "password": PASSWORD}, follow_redirects=False).status_code in (302, 303)
    return browser


@pytest.fixture
def world(clean_database, monkeypatch):
    monkeypatch.setattr("gcrm.tools.db_organizations.geocode", lambda city, country: None)
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug = 'default'")
        first = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO workspaces (slug, name) VALUES ('other-customer', 'Other') "
                       "ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name RETURNING id")
        second = cursor.fetchone()["id"]
    _user(first, "owner@first.example")
    _user(first, "viewer@first.example", role="spectator")
    _user(second, "owner@second.example")
    with workspace_scope(first):
        school = save_organization("VHS Musterstadt", "Augsburg", source="test_fixture")
        deal = next(d["id"] for d in get_deals("organization", school) if d["offer_slug"] == "consulting")
        add_deal_sale(deal, "2400", date(2026, 11, 8), "Courses", first, status="booked", expected_on=date(2027, 2, 1), months=4)
    return {"first": first, "second": second}


def test_the_page_shows_tiles_and_a_row_per_period_in_each_view(world):
    page = _browser("owner@first.example")
    month = page.get("/forecast?lang=en").text
    for text in ("This month", "Next month", "The month after", "This quarter", "Next quarter",
                 "This year", "Next year", "Months", "Quarters", "Years"):
        assert text in month
    assert "02.2027" in month and "600" in month
    assert "Q1 2027" in page.get("/forecast?view=quarter&lang=en").text
    assert "2027" in page.get("/forecast?view=year&lang=en").text
    assert "Forecast" in month and 'href="/forecast"' in month                       # in the navigation
    assert "Months" in page.get("/forecast?view=nonsense&lang=en").text              # a bad view falls back, no crash


def test_an_admin_sets_the_plan_and_the_page_shows_targets_and_what_is_missing(world):
    admin = _browser("owner@first.example")
    assert admin.post("/forecast/need", data={"monthly_need": "5000", "view": "month"}, follow_redirects=False).status_code == 303
    assert admin.post("/forecast/other-income", follow_redirects=False, data={
        "label": "Support payment", "amount_eur": "1500", "first_received_on": "01.11.2026", "payments": "6",
        "confirmed": "1", "view": "month"}).status_code == 303
    page = admin.get("/forecast?lang=en").text
    assert "Support payment" in page and "Confirmed" in page
    assert "5.000" in page.replace("\xa0", "") and "still missing" in page             # the target is the plain need
    with workspace_scope(world["first"]):
        assert get_plan()["monthly_need"] == Decimal("5000.00")


def test_a_viewer_can_look_but_not_change_the_plan(world):
    viewer = _browser("viewer@first.example")
    assert viewer.get("/forecast?lang=en").status_code == 200
    assert 'action="/forecast/need"' not in viewer.get("/forecast?lang=en").text       # no plan forms for a viewer
    assert viewer.post("/forecast/need", data={"monthly_need": "1"}, follow_redirects=False).status_code == 403
    with workspace_scope(world["first"]):
        assert get_plan()["monthly_need"] is None


def test_bad_plan_input_is_a_400_not_a_crash(world):
    admin = _browser("owner@first.example")
    assert admin.post("/forecast/need", data={"monthly_need": "lots"}, follow_redirects=False).status_code == 400
    assert admin.post("/forecast/need", data={"monthly_need": "-5"}, follow_redirects=False).status_code == 400
    bad = {"label": "x", "amount_eur": "100", "first_received_on": "01.11.2026", "payments": "3"}
    assert admin.post("/forecast/other-income", data={**bad, "first_received_on": "nonsense"}, follow_redirects=False).status_code == 400
    assert admin.post("/forecast/other-income", data={**bad, "payments": "0"}, follow_redirects=False).status_code == 400
    assert admin.post("/forecast/other-income", data={**bad, "amount_eur": "0"}, follow_redirects=False).status_code == 400


def test_confirming_and_removing_other_income_works_only_inside_ones_own_workspace(world):
    with workspace_scope(world["first"]):
        line = add_other_income("Possible follow-on", Decimal("300"), date(2027, 5, 1), 15, False)
    stranger = _browser("owner@second.example")
    assert stranger.post(f"/forecast/other-income/{line}/confirmed", data={"confirmed": "1"}, follow_redirects=False).status_code == 404
    assert stranger.post(f"/forecast/other-income/{line}/delete", follow_redirects=False).status_code == 404
    owner = _browser("owner@first.example")
    assert owner.post(f"/forecast/other-income/{line}/confirmed", data={"confirmed": "1"}, follow_redirects=False).status_code == 303
    with workspace_scope(world["first"]):
        assert get_plan()["other_income"][0]["confirmed"] is True
    assert owner.post(f"/forecast/other-income/{line}/delete", follow_redirects=False).status_code == 303
    with workspace_scope(world["first"]):
        assert get_plan()["other_income"] == []


def test_another_workspace_sees_none_of_this_workspaces_money_or_plan(world):
    with workspace_scope(world["first"]):
        add_other_income("Private support", Decimal("1234"), date(2026, 11, 1), 6, True)
    page = _browser("owner@second.example").get("/forecast?lang=en").text.replace("\xa0", " ")
    assert "Private support" not in page and "1.234" not in page      # the other workspace's plan
    assert "600,00 €" not in page and "600 €" not in page             # nor its contract payments


def test_the_plan_form_takes_the_first_month_and_income_lines_take_the_month_they_cover(world):
    admin = _browser("owner@first.example")
    assert admin.post("/forecast/need", data={"monthly_need": "5000", "start_month": "01.10.2026", "view": "month"},
                      follow_redirects=False).status_code == 303
    assert admin.post("/forecast/other-income", follow_redirects=False, data={
        "label": "Support payment", "amount_eur": "1500", "first_received_on": "01.11.2026", "covers_from": "01.10.2026",
        "payments": "6", "confirmed": "1", "view": "month"}).status_code == 303
    with workspace_scope(world["first"]):
        plan = get_plan()
    assert plan["start_month"] == date(2026, 10, 1) and plan["other_income"][0]["covers_from"] == date(2026, 10, 1)
    page = admin.get("/forecast?lang=en").text.replace("\xa0", " ")
    assert "Other income" in page and "1.500" in page


def test_an_income_line_can_be_edited_from_the_page(world):
    with workspace_scope(world["first"]):
        line = add_other_income("Support", Decimal("1000"), date(2026, 11, 1), 3, False)
    admin = _browser("owner@first.example")
    page = admin.get("/forecast?lang=en").text
    assert f'/forecast/other-income/{line}/edit' in page
    assert admin.post(f"/forecast/other-income/{line}/edit", follow_redirects=False, data={
        "label": "Support payment", "amount_eur": "1500", "first_received_on": "01.11.2026", "covers_from": "01.10.2026",
        "payments": "6", "confirmed": "1", "view": "month"}).status_code == 303
    with workspace_scope(world["first"]):
        edited = get_plan()["other_income"][0]
    assert (edited["label"], edited["amount_eur"], edited["covers_from"]) == ("Support payment", Decimal("1500.00"), date(2026, 10, 1))
    stranger = _browser("owner@second.example")
    assert stranger.post(f"/forecast/other-income/{line}/edit", follow_redirects=False, data={
        "label": "Hijacked", "amount_eur": "1", "first_received_on": "01.11.2026", "payments": "1"}).status_code == 404
    assert admin.post(f"/forecast/other-income/{line}/edit", follow_redirects=False, data={
        "label": "", "amount_eur": "1", "first_received_on": "01.11.2026", "payments": "1"}).status_code == 400


def test_other_income_sits_left_of_total_and_is_part_of_it(world):
    admin = _browser("owner@first.example")
    admin.post("/forecast/need", data={"monthly_need": "5000", "view": "month"}, follow_redirects=False)
    admin.post("/forecast/other-income", follow_redirects=False, data={
        "label": "Support payment", "amount_eur": "1500", "first_received_on": "01.11.2026", "payments": "6",
        "confirmed": "1", "view": "month"})
    page = admin.get("/forecast?lang=en").text
    header = page[page.index("<thead>"):page.index("</thead>")]
    order = [header.index(label) for label in ("Collected", "Contracted", "Booked", "Expected", "Secured",
                                              "Other income", "Total", "Target", "Still missing")]
    assert order == sorted(order), "columns must run Collected, Contracted, Booked, Expected, Secured, Other income, Total, Target, Still missing"
