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
    order = [header.index(label) for label in ("Collected", "Contracted", "Booked", "Expected", "Subtotal",
                                              "Other income", "Grand total", "Target", "Still missing")]
    assert order == sorted(order), "columns must run Collected, Contracted, Booked, Expected, Subtotal, Other income, Grand total, Target, Still missing"


def test_the_page_has_no_secured_column_and_calls_the_last_sum_the_grand_total(world):
    page = _browser("owner@first.example").get("/forecast?lang=en").text
    assert "Secured" not in page and "secured" not in page
    assert "Subtotal" in page and "Grand total" in page


def test_the_page_leaves_out_months_before_the_business_started(world):
    admin = _browser("owner@first.example")
    assert "09.2026" in admin.get("/forecast?lang=en").text                          # listed until a first month is set
    admin.post("/forecast/need", data={"monthly_need": "5000", "start_month": "01.10.2026", "view": "month"},
               follow_redirects=False)
    page = admin.get("/forecast?lang=en").text
    table = page[page.index("<tbody>"):page.index("</tbody>")]
    assert "09.2026" not in table and "10.2026" in table


def test_the_months_view_runs_through_the_end_of_next_year(world):
    page = _browser("owner@first.example").get("/forecast?lang=en").text
    table = page[page.index("<tbody>"):page.index("</tbody>")]
    year = date.today().year
    assert f"12.{year + 1}" in table and f"01.{year}" in table
    assert f"01.{year + 2}" not in table


def test_the_forecast_page_has_the_contract_flow_section_below_the_table_with_a_range_switch(world):
    page = _browser("owner@first.example").get("/forecast?lang=en").text
    assert page.index("<tbody>") < page.index('id="contract-flow"') < page.index('id="plan"')
    section = page[page.index('id="contract-flow"'):page.index('id="plan"')]
    for text in ("Contract flow", "3 months", "1 year", "Whole business", "New business per week",
                 "Total won so far (running total)", "Money in (running total)"):
        assert text in section
    assert section.count("<svg") == 3 and section.count("<figure") == 3
    assert 'name="flow" value="3m"' in section and 'name="flow" value="year"' in section and 'name="flow" value="all"' in section
    assert 'aria-current="true"' in section                                  # the chosen range is marked


def test_the_range_is_chosen_with_the_flow_parameter_and_nonsense_falls_back(world):
    browser = _browser("owner@first.example")
    weekly = browser.get("/forecast?flow=3m&lang=en").text
    assert "New business per week" in weekly
    yearly = browser.get("/forecast?flow=year&lang=en").text
    assert "New business per month" in yearly
    assert "New business per week" in browser.get("/forecast?flow=decade&lang=en").text          # the default: 3 months, by week
    assert "New business per month" in browser.get("/forecast?flow=all&lang=en").text
    assert 'name="flow" value="year"' in browser.get("/forecast?flow=year&view=quarter&lang=en").text


def test_the_view_buttons_keep_the_chosen_range_and_the_range_buttons_keep_the_view(world):
    page = _browser("owner@first.example").get("/forecast?flow=3m&view=quarter&lang=en").text
    assert page.count('<input type="hidden" name="flow" value="3m"') == 1             # in the Months/Quarters/Years form
    section = page[page.index('id="contract-flow"'):page.index('id="plan"')]
    assert '<input type="hidden" name="view" value="quarter"' in section


def test_the_charts_show_the_figures_of_the_workspace_and_the_target_line_once_a_plan_exists(world):
    admin = _browser("owner@first.example")
    admin.post("/forecast/need", data={"monthly_need": "5000", "start_month": "01.10.2026", "view": "month"}, follow_redirects=False)
    with workspace_scope(world["first"]):
        add_deal_sale(next(d["id"] for d in get_deals("organization", save_organization("Chart Firm", "Ulm", source="test_fixture"))
                           if d["offer_slug"] == "consulting"), "1200", date(2026, 10, 20), "job", world["first"], status="expected")
    page = admin.get("/forecast?flow=all&lang=en").text.replace("\xa0", " ")
    section = page[page.index('id="contract-flow"'):page.index('id="plan"')]
    assert "Money in vs target (running total)" in section and "chart-line--ref" in section
    assert "10.2026: 1.200 € · 1 deal · Expected 1.200 €" in section and "10.2026: 1.200 € in total" in section
    assert "Kessler" not in section


def test_a_viewer_can_see_the_charts_and_another_workspace_sees_none_of_this_ones_money(world):
    with workspace_scope(world["first"]):
        add_deal_sale(next(d["id"] for d in get_deals("organization", save_organization("Private Firm", "Ulm", source="test_fixture"))
                           if d["offer_slug"] == "consulting"), "4321", date.today(), "", world["first"], status="booked")
    assert "contract-flow" in _browser("viewer@first.example").get("/forecast?lang=en").text
    other = _browser("owner@second.example").get("/forecast?lang=en").text.replace("\xa0", " ")
    assert "4.321" not in other and "Nothing entered yet in this range." in other


def test_the_charts_follow_the_language(world):
    browser = _browser("owner@first.example")
    with db() as connection:
        connection.cursor().execute("UPDATE users SET ui_language = 'de' WHERE email = 'owner@first.example'")
    browser.post("/settings/language", data={"ui_language": "de"})
    section = browser.get("/forecast").text
    section = section[section.index('id="contract-flow"'):section.index('id="plan"')]
    assert "Vertragsfluss" in section and "Neues Geschäft pro Woche" in section and "Gesamtes Geschäft" in section


def test_the_outlook_is_a_fourth_range_with_a_projection_line_and_the_target_ahead(world):
    admin = _browser("owner@first.example")
    admin.post("/forecast/need", data={"monthly_need": "5000", "start_month": "01.10.2026", "view": "month"}, follow_redirects=False)
    with workspace_scope(world["first"]):
        add_deal_sale(next(d["id"] for d in get_deals("organization", save_organization("Outlook Firm", "Ulm", source="test_fixture"))
                           if d["offer_slug"] == "consulting"), "1200", date(2026, 10, 20), "job", world["first"], status="booked",
                      expected_on=date(2027, 3, 1))
        add_deal_sale(next(d["id"] for d in get_deals("organization", save_organization("Undated Firm", "Ulm", source="test_fixture"))
                           if d["offer_slug"] == "consulting"), "800", date(2026, 10, 21), "no date", world["first"], status="booked")
    page = admin.get("/forecast?flow=outlook&lang=en").text.replace("\xa0", " ")
    section = page[page.index('id="contract-flow"'):page.index('id="plan"')]
    assert 'name="flow" value="outlook"' in section and "Outlook" in section
    assert "Money in, projection and target (running total)" in section
    assert "chart-line--smooth" in section and "chart-line--projection" in section and "chart-line--ref" in section
    assert "projected" in section and "by month end" in section
    assert "1 payment worth 800 € has no due day yet" in section
    assert "New business per month" in section                               # the first two charts are still there
    assert section.count("stat-chart--wide") == 1                            # the outlook chart spans the page
    assert "stat-chart--wide" not in admin.get("/forecast?flow=3m&lang=en").text


def test_the_outlook_keeps_the_chosen_view_and_the_other_ranges_still_work(world):
    browser = _browser("owner@first.example")
    page = browser.get("/forecast?flow=outlook&view=quarter&lang=en").text
    assert '<input type="hidden" name="flow" value="outlook"' in page
    assert "Money in (running total)" in browser.get("/forecast?flow=3m&lang=en").text       # no plan: just money in


def test_the_outlook_follows_the_language(world):
    browser = _browser("owner@first.example")
    browser.post("/settings/language", data={"ui_language": "de"})
    section = browser.get("/forecast?flow=outlook").text
    section = section[section.index('id="contract-flow"'):section.index('id="plan"')]
    assert "Ausblick" in section and "Eingang und Prognose (Laufende Summe)" in section


def test_the_outlook_lists_the_sales_with_no_due_day_as_links_to_fix_them(world):
    admin = _browser("owner@first.example")
    with workspace_scope(world["first"]):
        org = save_organization("Eckert Schulen", "Augsburg", source="test_fixture")
        add_deal_sale(next(d["id"] for d in get_deals("organization", org) if d["offer_slug"] == "consulting"),
                      "800", date(2026, 10, 21), "interview", world["first"], status="expected")
    page = admin.get("/forecast?flow=outlook&lang=en").text.replace("\xa0", " ")
    section = page[page.index('id="contract-flow"'):page.index('id="plan"')]
    assert f'href="/organizations/{org}#sales"' in section and "Eckert Schulen" in section and "800 €" in section
    assert "Expected" in section[section.index("Eckert Schulen"):]
    assert "contract-flow-undated" in section
    other = _browser("owner@second.example").get("/forecast?flow=outlook&lang=en").text
    assert "Eckert Schulen" not in other                                       # another workspace never sees it


def test_an_admin_enters_the_new_sales_he_expects_and_the_outlook_gets_a_blue_line(world):
    admin = _browser("owner@first.example")
    outlook = "/forecast?flow=outlook&lang=en"
    section = lambda page: page[page.index('id="contract-flow"'):page.index('id="plan"')]       # noqa: E731
    assert "chart-line--assumed" not in section(admin.get(outlook).text)                       # nothing entered: no blue line
    plan = admin.get(outlook).text
    assert 'action="/forecast/new-sales"' in plan and "Expected new sales per month" in plan
    reply = admin.post("/forecast/new-sales", data={"expected_new_monthly": "1500,50", "view": "quarter"}, follow_redirects=False)
    assert reply.status_code == 303 and "view=quarter" in reply.headers["location"] and "flow=outlook" in reply.headers["location"]
    with workspace_scope(world["first"]):
        assert get_plan()["expected_new_monthly"] == Decimal("1500.50") and get_plan()["monthly_need"] is None
    page = admin.get(outlook).text.replace("\xa0", " ")
    assert "chart-line--assumed" in section(page) and "with expected new sales" in section(page)
    assert "a month of new sales you expect to book" in section(page)
    assert "chart-line--assumed" not in section(admin.get("/forecast?flow=3m&lang=en").text)    # only the outlook has the line
    assert 'value="1500.50"' in page
    admin.post("/forecast/new-sales", data={"expected_new_monthly": ""}, follow_redirects=False)  # blank clears it
    with workspace_scope(world["first"]):
        assert get_plan()["expected_new_monthly"] is None
    assert "chart-line--assumed" not in section(admin.get(outlook).text)


def test_the_new_sales_form_is_for_admins_and_rejects_nonsense(world):
    viewer, admin = _browser("viewer@first.example"), _browser("owner@first.example")
    assert 'action="/forecast/new-sales"' not in viewer.get("/forecast?lang=en").text
    assert viewer.post("/forecast/new-sales", data={"expected_new_monthly": "900"}, follow_redirects=False).status_code == 403
    for bad in ("lots", "-5"):
        assert admin.post("/forecast/new-sales", data={"expected_new_monthly": bad}, follow_redirects=False).status_code == 400
    with workspace_scope(world["first"]):
        assert get_plan()["expected_new_monthly"] is None
    with workspace_scope(world["second"]):
        assert get_plan()["expected_new_monthly"] is None


def test_the_blue_line_follows_the_language_and_a_viewer_sees_the_figure(world):
    admin = _browser("owner@first.example")
    admin.post("/forecast/new-sales", data={"expected_new_monthly": "1000"}, follow_redirects=False)
    admin.post("/settings/language", data={"ui_language": "de"})
    german = admin.get("/forecast?flow=outlook").text.replace("\xa0", " ")
    assert "mit erwarteten Neuverkäufen" in german and "Erwartete Neuverkäufe pro Monat" in german
    viewer = _browser("viewer@first.example").get("/forecast?flow=outlook&lang=en").text.replace("\xa0", " ")
    assert "Expected new sales per month" in viewer and 'name="expected_new_monthly"' not in viewer


def test_the_months_each_booking_pays_are_a_number_or_the_letter_i_and_zero_is_refused(world):
    admin = _browser("owner@first.example")
    for typed, stored in (("", 1), ("6", 6), ("i", None), ("I", None), ("\u221e", None), (" 12 ", 12)):
        assert admin.post("/forecast/new-sales", follow_redirects=False,
                          data={"expected_new_monthly": "1000", "new_sales_months": typed}).status_code == 303
        with workspace_scope(world["first"]):
            assert get_plan()["expected_new_months"] == stored, typed
    for bad in ("0", "-3", "121", "forever", "2.5"):
        assert admin.post("/forecast/new-sales", follow_redirects=False,
                          data={"expected_new_monthly": "1000", "new_sales_months": bad}).status_code == 400, bad
    admin.post("/forecast/new-sales", data={"expected_new_monthly": "1000", "new_sales_months": "i"}, follow_redirects=False)
    page = admin.get("/forecast?flow=outlook&lang=en").text
    assert 'name="new_sales_months"' in page and "every month from then on" in page.replace("\xa0", " ")
