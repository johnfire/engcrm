"""New contracts from the deal cards, and the cards listing contracts, on the real schema through real logins."""
import re
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import gcrm.api.main as main
from gcrm.api.jwt_auth import create_token
from gcrm.api.security import hash_password
from gcrm.api.templates import eur
from gcrm.db.connection import db
from gcrm.tools.db_contracts import contracts_by_deal
from gcrm.tools.db_deals import set_organization_deal
from gcrm.tools.db_organizations import save_organization
from gcrm.tools.db_people import save_person
from gcrm.tools.deal_money import add_deal_sale, set_sale_status
from gcrm.tools.deal_records import add_deal, get_deals
from gcrm.tools.statistics import add_sale
from gcrm.workspace_context import workspace_scope

pytestmark = pytest.mark.integration
PASSWORD = "a-long-test-password-1"
TODAY = date.today()


def _days(n):
    return TODAY + timedelta(days=n)


def _user(workspace, email, role="admin"):
    with db() as connection:
        connection.cursor().execute(
            "INSERT INTO users (email, name, password_hash, role, workspace_id, is_active) VALUES (%s, %s, %s, %s, %s, TRUE)",
            (email, email.split("@")[0], hash_password(PASSWORD), role, workspace))


def _browser(email="owner@first.example"):
    browser = TestClient(main.app)
    assert browser.post("/login", data={"email": email, "password": PASSWORD}, follow_redirects=False).status_code in (302, 303)
    return browser


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
    with workspace_scope(first):
        school = save_organization("VHS Musterstadt", "Augsburg", source="test_fixture")
        freelancer = save_person("Pat Freelancer", source="test_fixture")
        with db() as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT offer_id_for(%s, 'consulting') AS id", (first,))
            own = add_deal("person", freelancer, cursor.fetchone()["id"])
        deal = next(d["id"] for d in get_deals("organization", school) if d["offer_slug"] == "consulting")
    with workspace_scope(second):
        foreign = save_organization("Kessler Logistik", "Ulm", source="test_fixture")
        foreign_deal = next(d["id"] for d in get_deals("organization", foreign) if d["offer_slug"] == "consulting")
        add_deal_sale(foreign_deal, "5555", TODAY, "Kessler secret", second, status="booked")
    return {"first": first, "second": second, "school": school, "deal": deal, "own": own, "freelancer": freelancer,
            "foreign_deal": foreign_deal}


def _count(table):
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute(f"SELECT count(*) AS n FROM {table} WHERE workspace_id = (SELECT id FROM workspaces WHERE slug = 'default')")
        return cursor.fetchone()["n"]


def _contract(title):
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id, kind, deal_id FROM contracts WHERE title = %s", (title,))
        return dict(cursor.fetchone())


def _sales_card(html):
    return re.search(r'id="sales".*?</section>', html, re.S).group(0)


def _link(contract_id, title):
    return f'<a class="contract-title" href="/contracts/{contract_id}">{title}</a>'


NEW = {"amount_eur": "2400", "won_on": TODAY.isoformat(), "status": "booked", "expected_on": _days(10).isoformat()}


# --- making a contract ---------------------------------------------------------

def test_a_new_contract_from_the_organization_page_shows_there_and_on_the_contracts_page(world):
    browser = _browser()
    response = browser.post(f"/organizations/{world['school']}/sales", follow_redirects=False,
                            data={**NEW, "title": "AI course for Kaufleute", "kind": "teaching_course"})
    assert response.status_code == 303
    contract = _contract("AI course for Kaufleute")
    assert (contract["kind"], contract["deal_id"]) == ("teaching_course", world["deal"])
    card = _sales_card(browser.get(f"/organizations/{world['school']}?lang=en").text)
    for text in (_link(contract["id"], "AI course for Kaufleute"), "Teaching course", eur(2400), "Upcoming",
                 _days(10).strftime("%d.%m.%Y")):
        assert text in card, text
    assert _link(contract["id"], "AI course for Kaufleute") in browser.get("/contracts/?lang=en").text


def test_a_monthly_contract_from_the_organization_page_is_one_contract_with_its_payments(world):
    _browser().post(f"/organizations/{world['school']}/sales", follow_redirects=False,
                    data={**NEW, "amount_eur": "500", "schedule": "monthly", "months": "3", "title": "Monthly coaching", "kind": "consulting"})
    assert _count("contracts") == 1 and _count("sales") == 3
    contract = _contract("Monthly coaching")
    card = _sales_card(_browser().get(f"/organizations/{world['school']}?lang=en").text)
    assert eur(1500) in card and card.count(_link(contract["id"], "Monthly coaching")) == 1


def test_a_new_contract_from_a_persons_deal_card_shows_on_their_page(world):
    browser = _browser()
    response = browser.post(f"/deals/{world['own']}/sales", follow_redirects=False,
                            data={**NEW, "title": "Coaching block", "kind": "workshop", "next": f"/people/{world['freelancer']}"})
    assert response.status_code == 303 and response.headers["location"] == f"/people/{world['freelancer']}"
    contract = _contract("Coaching block")
    page = browser.get(f"/people/{world['freelancer']}?lang=en").text
    assert _link(contract["id"], "Coaching block") in page and "Workshop" in page and "Upcoming" in page


@pytest.mark.parametrize("extra", [{}, {"title": "  "}, {"title": "x" * 201}, {"title": "Fine", "kind": "speech"}])
@pytest.mark.parametrize("target", ["organization", "person"])
def test_a_refused_title_or_kind_writes_neither_a_contract_nor_a_sale(world, target, extra):
    url = f"/organizations/{world['school']}/sales" if target == "organization" else f"/deals/{world['own']}/sales"
    assert _browser().post(url, data={**NEW, **extra}, follow_redirects=False).status_code == 400
    assert _count("contracts") == 0 and _count("sales") == 0


def test_a_new_contract_without_a_kind_is_other(world):
    _browser().post(f"/organizations/{world['school']}/sales", data={**NEW, "title": "No kind named"}, follow_redirects=False)
    assert _contract("No kind named")["kind"] == "other"


def test_the_insert_path_takes_a_kind_and_an_unknown_one_writes_nothing(world):
    add_sale(world["first"], world["school"], "100", TODAY, "", world["deal"], status="booked", title="By code", kind="workshop")
    assert _contract("By code")["kind"] == "workshop"
    with pytest.raises(ValueError):
        add_deal_sale(world["own"], "100", TODAY, "", world["first"], status="booked", title="Bad", kind="speech")
    assert _count("contracts") == 1 and _count("sales") == 1


def test_a_spectator_cannot_make_a_contract(world):
    viewer = _browser("viewer@first.example")
    for url in (f"/organizations/{world['school']}/sales", f"/deals/{world['own']}/sales"):
        assert viewer.post(url, data={**NEW, "title": "Sneaky"}, follow_redirects=False).status_code == 403
    assert _count("contracts") == 0


# --- what the cards show ---------------------------------------------------

def test_the_cards_list_contracts_with_their_timing_instead_of_payment_rows(world):
    add_deal_sale(world["deal"], "100", TODAY, "Now job", world["first"], status="booked", work_from=_days(-5), work_to=_days(5))
    add_deal_sale(world["deal"], "200", TODAY, "Later job", world["first"], status="booked", work_from=_days(30), work_to=_days(40))
    add_deal_sale(world["deal"], "300", TODAY, "Old job", world["first"], status="booked", work_from=_days(-40), work_to=_days(-30), hours="3")
    lost = add_deal_sale(world["deal"], "400", TODAY, "Lost job", world["first"], status="booked")
    set_sale_status(world["deal"], lost, "cancelled", workspace_id=world["first"])
    html = _browser().get(f"/organizations/{world['school']}?lang=en").text
    card = _sales_card(html)
    order = re.findall(r'<a class="contract-title" href="/contracts/\d+">([^<]+)</a>', card)
    assert order == ["Now job", "Later job", "Lost job", "Old job"]          # running, upcoming, then finished (latest end first)
    rows = {title: re.search(rf'<li[^>]*>(?:(?!</li>).)*>{title}</a>.*?</li>', card, re.S).group(0) for title in order}
    assert "Running now" in rows["Now job"] and "Upcoming" in rows["Later job"] and "Finished" in rows["Old job"]
    assert "cancelled" in rows["Lost job"] and eur(400) not in rows["Lost job"]
    assert not re.search(r"/deals/\d+/(sales|series)/[^\"]+/(status|delete|work|due-day)", html)      # no payment controls here
    assert 'class="sale sale--' not in html
    assert "3 h" in card                                                        # the hours line the card always had
    assert 'name="title"' in card and 'name="kind"' in card and "New contract" in card and "Kessler secret" not in html


def test_an_organizations_card_lists_the_contracts_of_every_offer_naming_each(world):
    with workspace_scope(world["first"]):
        with db() as connection:
            set_organization_deal(connection.cursor(), world["school"], stage="prospect", offer="learnwohl")
        learn = next(d["id"] for d in get_deals("organization", world["school"]) if d["offer_slug"] == "learnwohl")
    add_deal_sale(world["deal"], "100", TODAY, "Consulting job", world["first"], status="booked")
    add_deal_sale(learn, "200", TODAY, "Learning job", world["first"], status="booked")
    card = _sales_card(_browser().get(f"/organizations/{world['school']}?lang=en").text)
    assert "Consulting job" in card and "Learning job" in card
    assert "Offer: LearnWohl" in card and "Offer: Consulting" in card


def test_the_new_contract_button_and_cards_are_in_german_too(world):
    add_deal_sale(world["deal"], "100", TODAY, "Auftrag", world["first"], status="booked", work_from=_days(30), work_to=_days(31))
    browser = _browser()
    browser.post("/settings/language", data={"ui_language": "de"})
    card = _sales_card(browser.get(f"/organizations/{world['school']}").text)
    assert "Neuer Vertrag" in card and "Anstehend" in card and "Vertragstitel" in card


def test_an_organization_without_contracts_says_so(world):
    card = _sales_card(_browser().get(f"/organizations/{world['school']}?lang=en").text)
    assert "No contracts here." in card and "contract-title" not in card


def test_contracts_for_deals_stay_inside_the_workspace_and_are_empty_for_no_deals(world):
    assert contracts_by_deal(world["first"], [world["foreign_deal"]], TODAY) == {}
    assert contracts_by_deal(world["first"], [], TODAY) == {}
    (found,) = contracts_by_deal(world["second"], [world["foreign_deal"]], TODAY)[world["foreign_deal"]]
    assert found["title"] == "Kessler secret" and found["timing"] == "running" and found["summary"]["value"] == Decimal("5555")


# --- the Contracts page ------------------------------------------------------

def test_the_contracts_page_sends_an_admin_to_the_customer_for_a_new_contract(world):
    html = _browser().get("/contracts/?lang=en").text
    assert re.search(r'<a class="btn-secondary[^"]*" href="/organizations/">New contract</a>', html)
    assert "Open the customer" in html and 'href="/people/"' in html
    viewer = _browser("viewer@first.example").get("/contracts/?lang=en").text
    assert "New contract" not in viewer


# --- the phone ---------------------------------------------------------------

def test_the_phone_still_records_a_sale_which_gets_a_contract_and_its_answers_are_unchanged(world):
    phone = TestClient(main.app)
    headers = {"Authorization": f"Bearer {create_token('admin')}"}
    created = phone.post(f"/api/deals/{world['deal']}/sales", headers=headers,
                         json={"amount_eur": "300", "won_on": TODAY.isoformat(), "description": "From the phone", "status": "booked"})
    assert created.status_code == 201
    assert _contract("From the phone")["kind"] == "other"
    (deal,) = [d for d in phone.get(f"/api/contacts/{world['school']}/deals", headers=headers).json() if d["id"] == world["deal"]]
    assert set(deal["money"]) == {"sales_total", "pipeline_total", "expected_total", "sales", "subscriptions", "running"}
    assert not any("contract" in key for key in deal["money"]["sales"][0])


# --- the contract page's payment rows ----------------------------------------

def _payment_rows(html):
    return re.search(r'<fieldset class="contract-payments".*?</fieldset>', html, re.S).group(0)


def test_the_contract_page_does_not_repeat_its_title_and_the_won_on_day_in_each_payment(world):
    add_deal_sale(world["deal"], "900", date(2026, 2, 3), "Repeated title", world["first"], status="booked",
                  expected_on=date(2027, 3, 1), months=3)
    contract = _contract("Repeated title")["id"]
    rows = _payment_rows(_browser().get(f"/contracts/{contract}?open=payments&lang=en").text)
    assert "Repeated title" not in rows and "03.02.2026" not in rows
    assert "payment 1 of 3" in rows and "01.03.2027" in rows


def test_a_payment_note_that_says_something_else_than_the_title_is_still_shown(world):
    add_deal_sale(world["deal"], "100", date(2026, 2, 3), "Second instalment note", world["first"], status="booked", title="Year plan")
    contract = _contract("Year plan")["id"]
    rows = _payment_rows(_browser().get(f"/contracts/{contract}?open=payments&lang=en").text)
    assert "Second instalment note" in rows and "03.02.2026" not in rows


# --- the card's heading ----------------------------------------------------

@pytest.mark.parametrize("language,heading", [("en", "Contracts"), ("de", "Verträge")])
def test_the_cards_that_list_contracts_are_headed_contracts_and_keep_their_anchor(world, language, heading):
    browser = _browser()
    browser.post("/settings/language", data={"ui_language": language})
    organization = browser.get(f"/organizations/{world['school']}").text
    card = _sales_card(organization)                                   # the id other pages link to stays "sales"
    assert f"<h2>{heading}</h2>" in card and "<h2>Sales</h2>" not in card and "<h2>Verkäufe</h2>" not in card
    person = browser.get(f"/people/{world['freelancer']}").text
    summary = re.search(r'<details class="deal-card__sales".*?<summary>(.*?)</summary>', person, re.S).group(1)
    assert summary.strip() == heading


def test_the_payment_charts_link_to_an_anchor_the_organization_page_still_has(world):
    chart_code = (Path(__file__).parents[2] / "gcrm" / "flow_charts.py").read_text()
    assert "#sales" in chart_code and 'id="sales"' in _browser().get(f"/organizations/{world['school']}").text
