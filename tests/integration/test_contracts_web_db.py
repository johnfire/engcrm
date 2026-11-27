"""The Contracts list on the real schema: the three sections, the filters, the totals, and that it counts
exactly the sales the Forecast counts. Dates are relative to today because the page groups by today."""
import json
import re
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import gcrm.api.main as main
from gcrm.api.security import hash_password
from gcrm.api.templates import eur
from gcrm.db.connection import db
from gcrm.tools.db_contracts import list_contracts
from gcrm.tools.db_deals import set_organization_deal
from gcrm.tools.db_organizations import save_organization
from gcrm.tools.db_people import save_person
from gcrm.tools.deal_money import add_deal_sale, delete_deal_sale, set_sale_status
from gcrm.tools.deal_records import add_deal, get_deals
from gcrm.tools.revenue import business_revenue
from gcrm.workspace_context import workspace_scope

pytestmark = pytest.mark.integration
PASSWORD = "a-long-test-password-1"
EN_FILE = Path(__file__).parents[2] / "gcrm" / "i18n" / "en.json"
TODAY = date.today()


def _days(n):
    return TODAY + timedelta(days=n)


def _user(workspace, email, role="admin"):
    with db() as connection:
        connection.cursor().execute(
            "INSERT INTO users (email, name, password_hash, role, workspace_id, is_active) VALUES (%s, %s, %s, %s, %s, TRUE)",
            (email, email.split("@")[0], hash_password(PASSWORD), role, workspace))


def _browser(email):
    browser = TestClient(main.app)
    assert browser.post("/login", data={"email": email, "password": PASSWORD}, follow_redirects=False).status_code in (302, 303)
    return browser


def _kind(title, kind):
    with db() as connection:
        connection.cursor().execute("UPDATE contracts SET kind = %s WHERE title = %s", (kind, title))


def _id(title):
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM contracts WHERE title = %s", (title,))
        return cursor.fetchone()["id"]


@pytest.fixture
def world(clean_database, monkeypatch):
    monkeypatch.setattr("gcrm.tools.db_organizations.geocode", lambda city, country: None)
    monkeypatch.setattr("gcrm.tools.db_people.geocode", lambda city, country: None)
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
        gone = save_organization("Verschwunden GmbH", "Ulm", source="test_fixture")
        deal = next(d["id"] for d in get_deals("organization", school) if d["offer_slug"] == "consulting")
        gone_deal = next(d["id"] for d in get_deals("organization", gone) if d["offer_slug"] == "consulting")
        with db() as connection:
            set_organization_deal(connection.cursor(), school, stage="prospect", offer="learnwohl")
        learn = next(d["id"] for d in get_deals("organization", school) if d["offer_slug"] == "learnwohl")
        # running: four monthly payments of 600, 40 hours in all
        add_deal_sale(deal, "2400", _days(-40), "Year course AI", first, status="booked", expected_on=_days(10), months=4,
                      hours="40", work_from=_days(-30), work_to=_days(120))
        # upcoming
        add_deal_sale(deal, "800", _days(-5), "Autumn workshop", first, status="booked", expected_on=_days(60),
                      work_from=_days(60), work_to=_days(61))
        # finished, money still to come
        add_deal_sale(deal, "500", _days(-95), "Old consulting", first, status="booked", expected_on=_days(-60),
                      work_from=_days(-90), work_to=_days(-60))
        # finished and paid
        add_deal_sale(deal, "300", _days(-100), "Done workshop", first, status="collected", collected_on=_days(-98),
                      work_from=_days(-100), work_to=_days(-99))
        # cancelled, with dates that would make it run now
        lost = add_deal_sale(deal, "999", _days(-20), "Fell through", first, status="booked", expected_on=_days(5),
                             work_from=_days(-10), work_to=_days(10))
        set_sale_status(deal, lost, "cancelled", workspace_id=first)
        # no work window and no due day: only the day it was won
        add_deal_sale(learn, "200", _days(-5), "LearnWohl pilot", first, status="collected", collected_on=_days(-5))
        # a sale that is deleted again takes its contract with it
        sale = add_deal_sale(deal, "123", _days(-3), "Deleted job", first, status="booked")
        delete_deal_sale(deal, sale, first)
        # an organization that is deleted takes its contracts off every page
        add_deal_sale(gone_deal, "777", _days(-3), "Orphan job", first, status="booked")
        with db() as connection:
            connection.cursor().execute("UPDATE contacts SET deleted_at = NOW() WHERE id = %s", (gone,))
            # a live contract with no payment at all must not break the page
            connection.cursor().execute("INSERT INTO contracts (workspace_id, deal_id, title) VALUES (%s, %s, 'Empty shell')",
                                        (first, deal))
    _kind("Year course AI", "teaching_course")
    _kind("Autumn workshop", "workshop")
    _kind("Done workshop", "workshop")
    with workspace_scope(second):
        other = save_organization("Kessler Logistik", "Ulm", source="test_fixture")
        add_deal_sale(next(d["id"] for d in get_deals("organization", other) if d["offer_slug"] == "consulting"), "5555",
                      _days(-1), "Kessler secret", second, status="booked")
    return {"first": first, "second": second, "deal": deal}


def _section(html, key):
    match = re.search(rf'id="contracts-{key}".*?(?=id="contracts-(?:running|upcoming|finished)"|</main>)', html, re.S)
    assert match, f"no {key} section"
    return match.group(0)


def _titles(section_html):
    return re.findall(r'<a class="contract-title" href="/contracts/\d+">([^<]+)</a>', section_html)


def _row(html, title):
    match = re.search(rf'<tr id="contract-{_id(title)}".*?</tr>', html, re.S)
    assert match, f"no row for {title}"
    return match.group(0)


def _page(world, query="", user="owner@first.example"):
    return _browser(user).get(f"/contracts/?lang=en{query}")


# --- the data ----------------------------------------------------------------

def test_the_query_returns_each_live_contract_with_its_summary_computed_from_its_live_payments(world):
    with workspace_scope(world["first"]):
        found = {c["title"]: c for c in list_contracts(world["first"], None, None)}
    assert set(found) == {"Year course AI", "Autumn workshop", "Old consulting", "Done workshop", "Fell through",
                          "LearnWohl pilot", "Empty shell"}
    year = found["Year course AI"]
    assert (year["summary"]["value"], year["summary"]["hours"], year["summary"]["rate"]) == (Decimal("2400"), Decimal("40"), Decimal("60.00"))
    assert (year["summary"]["start"], year["summary"]["end"]) == (_days(-30), _days(120))
    assert year["summary"]["payments"] == 4 and year["kind"] == "teaching_course"
    assert (year["owner_name"], year["offer_slug"]) == ("VHS Musterstadt", "consulting")
    assert year["organization_id"] is not None and year["person_id"] is None
    assert found["Fell through"]["summary"]["cancelled"] is True and found["Fell through"]["summary"]["value"] == 0
    pilot = found["LearnWohl pilot"]["summary"]
    assert (pilot["start"], pilot["end"]) == (_days(-5), _days(-5))                  # only the day it was won
    assert found["Empty shell"]["summary"]["payments"] == 0


def test_the_kind_and_offer_filters_narrow_the_query(world):
    with workspace_scope(world["first"]):
        assert {c["title"] for c in list_contracts(world["first"], None, "workshop")} == {"Autumn workshop", "Done workshop"}
        assert {c["title"] for c in list_contracts(world["first"], "learnwohl", None)} == {"LearnWohl pilot"}
        assert list_contracts(world["first"], "learnwohl", "workshop") == []


def test_the_query_never_returns_another_workspaces_contracts_even_without_row_security(world):
    """No workspace scope here: the operator connection bypasses row security, so only the query's own
    workspace filter keeps the other workspace out."""
    titles = {c["title"] for c in list_contracts(world["first"], None, None)}
    assert "Kessler secret" not in titles and "Year course AI" in titles
    assert {c["title"] for c in list_contracts(world["second"], None, None)} == {"Kessler secret"}


# --- the page ----------------------------------------------------------------

def test_the_page_puts_each_contract_in_its_section_in_the_agreed_order(world):
    html = _page(world).text
    assert _titles(_section(html, "running")) == ["Year course AI"]
    assert _titles(_section(html, "upcoming")) == ["Autumn workshop"]
    # finished: cancelled one (its dates reach furthest), then most recent end first, the one without dates last
    assert _titles(_section(html, "finished")) == ["Fell through", "LearnWohl pilot", "Old consulting", "Done workshop", "Empty shell"]
    for hidden in ("Deleted job", "Orphan job", "Kessler secret"):
        assert hidden not in html


def test_finished_is_collapsed_and_the_others_are_open(world):
    html = _page(world).text
    finished = re.search(r'<details[^>]*id="contracts-finished"[^>]*>', html)
    assert finished and not re.search(r"\bopen\b", finished.group(0))           # a closed <details>
    assert not re.search(r'<details[^>]*id="contracts-(running|upcoming)"', html)   # these two are always shown


def test_a_row_shows_company_title_kind_dates_value_hours_rate_and_collected_and_links_to_its_page(world):
    row = _row(_page(world).text, "Year course AI")
    contract_id = _id("Year course AI")
    for text in (f'href="/contracts/{contract_id}"', "VHS Musterstadt", "Teaching course", eur(2400), "40", eur(60), eur(0),
                 _days(-30).strftime("%d.%m.%Y"), _days(120).strftime("%d.%m.%Y")):
        assert text in row, text
    assert 'href="/organizations/' in row


def test_a_finished_contract_with_money_open_says_so_and_a_paid_one_does_not(world):
    html = _page(world).text
    assert f"{eur(500)} still open" in _row(html, "Old consulting")
    assert "still open" not in _row(html, "Done workshop")


def test_a_cancelled_contract_is_tagged_and_counts_for_nothing(world):
    html = _page(world).text
    row = _row(html, "Fell through")
    assert "cancelled" in row.lower() and eur(999) not in html


def test_an_empty_contract_is_shown_under_finished_with_zero_euros(world):
    row = _row(_page(world).text, "Empty shell")
    assert eur(0) in row and "Traceback" not in row


def test_the_top_line_and_each_section_total_value_hours_rate_and_collected(world):
    html = _page(world).text
    top = re.search(r'id="contracts-totals".*?</section>', html, re.S).group(0)
    # 2400 + 800 + 500 + 300 + 200 (the cancelled one, the deleted one and the empty one add nothing)
    for text in (eur(4200), "40", eur(60), eur(500)):
        assert text in top, text
    running = _section(html, "running").split("<table")[0]            # the heading carries count, value and hours
    assert eur(2400) in running and "40" in running and "1" in running
    finished = _section(html, "finished").split("<table")[0]
    assert eur(1000) in finished and "5" in finished                    # 500 + 300 + 200 of five contracts, one cancelled


def test_the_page_counts_exactly_the_sales_the_forecast_counts(world):
    with workspace_scope(world["first"]):
        listed = sum((c["summary"]["value"] for c in list_contracts(world["first"], None, None)), Decimal("0"))
        assert listed == business_revenue(world["first"])["total"]


def test_the_kind_filter_keeps_only_that_kind_and_a_nonsense_kind_is_ignored(world):
    html = _page(world, "&kind=workshop").text
    shown = _titles(_section(html, "upcoming")) + _titles(_section(html, "finished"))
    assert sorted(shown) == ["Autumn workshop", "Done workshop"] and _titles(_section(html, "running")) == []
    assert "Year course AI" in _page(world, "&kind=nonsense").text


def test_the_offer_filter_keeps_only_that_offer_and_is_remembered_in_the_session(world):
    browser = _browser("owner@first.example")
    html = browser.get("/contracts/?lang=en&offer=learnwohl").text
    assert _titles(_section(html, "finished")) == ["LearnWohl pilot"] and "Year course AI" not in html
    assert "Year course AI" not in browser.get("/contracts/?lang=en").text            # remembered
    assert "Year course AI" in browser.get("/contracts/?lang=en&offer=all").text


def test_another_workspace_sees_only_its_own_contracts(world):
    html = _page(world, user="owner@second.example").text
    assert "Kessler secret" in html
    for title in ("Year course AI", "Autumn workshop", "Old consulting"):
        assert title not in html


def test_everyone_signed_in_can_look_and_a_stranger_is_sent_to_the_login(world):
    assert "Year course AI" in _page(world, user="viewer@first.example").text
    response = TestClient(main.app).get("/contracts/", follow_redirects=False)
    assert response.status_code in (302, 303, 307) and "login" in response.headers["location"]
    assert "Year course AI" not in response.text


def test_the_page_is_in_the_navigation_and_shows_a_table_that_stacks_on_a_phone(world):
    html = _page(world).text
    assert 'href="/contracts/"' in html and "Contracts" in html
    assert 'data-label="' in _row(html, "Year course AI") and "contracts.css" in html


def test_every_text_is_translated_in_english_and_in_german(world):
    owner = _browser("owner@first.example")
    keys = [k for k in json.load(open(EN_FILE)) if k.startswith("contracts.")]
    english = owner.get("/contracts/").text
    owner.post("/settings/language", data={"ui_language": "de"})
    german = owner.get("/contracts/").text
    for html in (english, german):
        assert not [key for key in keys if key in html], "an untranslated key shows on the page"
    for text in ("Verträge", "Laufend", "Anstehend", "Abgeschlossen", "noch offen", "storniert", "Kunde"):
        assert text in german, text
    assert "Running now" in english and "Verträge" not in english


def test_a_person_owned_contract_is_listed_with_the_person(world):
    with workspace_scope(world["first"]):
        freelancer = save_person("Pat Freelancer", source="test_fixture")
        with db() as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT offer_id_for(%s, 'consulting') AS id", (world["first"],))
            deal = add_deal("person", freelancer, cursor.fetchone()["id"])
        add_deal_sale(deal, "400", _days(-2), "Coaching block", world["first"], status="booked")
    row = _row(_page(world).text, "Coaching block")
    assert "Pat Freelancer" in row and f'href="/people/{freelancer}"' in row


def test_every_cell_has_a_name_so_the_phone_layout_can_place_it_and_empty_ones_are_flagged(world):
    html = _page(world).text
    running = _row(html, "Year course AI")
    for cell in ("customer", "title", "kind", "dates", "value", "hours", "rate", "collected"):
        assert f'class="c-{cell}' in running, cell
    assert "contracts-empty" not in running                      # it has hours and a rate
    no_hours = _row(html, "Old consulting")
    assert re.search(r'class="[^"]*c-hours[^"]*contracts-empty', no_hours) and re.search(r'class="[^"]*c-rate[^"]*contracts-empty', no_hours)
    cancelled = _row(html, "Fell through")
    assert 'class="contracts-cancelled"' in cancelled or "contracts-cancelled" in cancelled
