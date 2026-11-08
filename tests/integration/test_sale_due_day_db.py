"""A sale's due day can be set or changed after it was entered, and is shown on every unreceived sale.
For a monthly contract the changed payment and the ones after it follow monthly from the new day."""
from datetime import date

import pytest
from fastapi.testclient import TestClient

import gcrm.api.main as main
from gcrm.api.security import hash_password
from gcrm.db.connection import db
from gcrm.tools.db_organizations import save_organization
from gcrm.tools.deal_money import add_deal_sale, set_sale_due_day, set_sale_status
from gcrm.tools.deal_records import DealNotFound, get_deals

pytestmark = pytest.mark.integration


@pytest.fixture
def firm(clean_database, monkeypatch):
    monkeypatch.setattr("gcrm.tools.db_organizations.geocode", lambda city, country: None)
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug = 'default'")
        workspace = cursor.fetchone()["id"]
    contact = save_organization("Eckert Musterschule", "Augsburg", pipeline_stage="prospect", source="test_fixture")
    other = save_organization("Other Firm", "Ulm", pipeline_stage="prospect", source="test_fixture")
    deals = {c: next(d["id"] for d in get_deals("organization", c) if d["offer_slug"] == "consulting") for c in (contact, other)}
    return {"contact": contact, "deal": deals[contact], "other_deal": deals[other], "workspace": workspace}


def _rows(deal):
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id, status, expected_on, collected_on, series_part FROM sales WHERE deal_id = %s "
                       "AND deleted_at IS NULL ORDER BY series_part NULLS FIRST, id", (deal,))
        return [dict(r) for r in cursor.fetchall()]


def test_an_expected_sale_without_a_due_day_can_be_given_one(firm):
    sale = add_deal_sale(firm["deal"], "5000", date(2026, 11, 8), "AI training", firm["workspace"], status="expected")
    assert _rows(firm["deal"])[0]["expected_on"] is None
    assert set_sale_due_day(firm["deal"], sale, date(2027, 2, 15), firm["workspace"]) == 1
    assert _rows(firm["deal"])[0]["expected_on"] == date(2027, 2, 15)
    assert set_sale_due_day(firm["deal"], sale, date(2027, 3, 1), firm["workspace"]) == 1      # and it can be changed again
    assert _rows(firm["deal"])[0]["expected_on"] == date(2027, 3, 1)


@pytest.mark.parametrize("status", ["booked", "contracted"])
def test_booked_and_contracted_sales_can_be_redated_too(firm, status):
    sale = add_deal_sale(firm["deal"], "900", date(2026, 11, 8), "", firm["workspace"], status=status, expected_on=date(2027, 1, 10))
    assert set_sale_due_day(firm["deal"], sale, date(2027, 4, 1), firm["workspace"]) == 1
    assert _rows(firm["deal"])[0]["expected_on"] == date(2027, 4, 1)


def test_a_received_or_cancelled_sale_keeps_its_day(firm):
    got = add_deal_sale(firm["deal"], "100", date(2026, 11, 8), "", firm["workspace"], status="collected", collected_on=date(2026, 11, 9))
    lost = add_deal_sale(firm["deal"], "200", date(2026, 11, 8), "", firm["workspace"], status="booked", expected_on=date(2027, 1, 1))
    set_sale_status(firm["deal"], lost, "cancelled", workspace_id=firm["workspace"])
    assert set_sale_due_day(firm["deal"], got, date(2027, 5, 5), firm["workspace"]) == 0
    assert set_sale_due_day(firm["deal"], lost, date(2027, 5, 5), firm["workspace"]) == 0
    assert [r["expected_on"] for r in _rows(firm["deal"])] == [None, date(2027, 1, 1)]


def test_a_monthly_contract_follows_from_the_changed_payment_and_what_was_received_stays(firm):
    add_deal_sale(firm["deal"], "2400", date(2026, 11, 8), "", firm["workspace"], status="booked", expected_on=date(2027, 2, 1), months=4)
    rows = _rows(firm["deal"])
    set_sale_status(firm["deal"], rows[0]["id"], "collected", collected_on=date(2027, 2, 3), workspace_id=firm["workspace"])
    assert set_sale_due_day(firm["deal"], rows[1]["id"], date(2027, 4, 15), firm["workspace"]) == 3
    assert [r["expected_on"] for r in _rows(firm["deal"])] == [date(2027, 2, 1), date(2027, 4, 15), date(2027, 5, 15), date(2027, 6, 15)]
    assert _rows(firm["deal"])[0]["collected_on"] == date(2027, 2, 3)


def test_moving_the_first_payment_moves_the_whole_schedule_and_short_months_are_clipped(firm):
    add_deal_sale(firm["deal"], "900", date(2026, 11, 8), "", firm["workspace"], status="contracted", expected_on=date(2027, 2, 1), months=3)
    first = _rows(firm["deal"])[0]["id"]
    assert set_sale_due_day(firm["deal"], first, date(2027, 1, 31), firm["workspace"]) == 3
    assert [r["expected_on"] for r in _rows(firm["deal"])] == [date(2027, 1, 31), date(2027, 2, 28), date(2027, 3, 31)]


def test_only_the_sales_of_that_deal_and_workspace_can_be_changed(firm):
    sale = add_deal_sale(firm["deal"], "500", date(2026, 11, 8), "", firm["workspace"], status="expected")
    assert set_sale_due_day(firm["other_deal"], sale, date(2027, 1, 1), firm["workspace"]) == 0     # not that deal's sale
    assert set_sale_due_day(firm["deal"], 999999, date(2027, 1, 1), firm["workspace"]) == 0
    with pytest.raises(DealNotFound):
        set_sale_due_day(999999, sale, date(2027, 1, 1), firm["workspace"])
    assert _rows(firm["deal"])[0]["expected_on"] is None


def _browser(firm):
    with db() as connection:
        connection.cursor().execute(
            "INSERT INTO users (email, name, password_hash, role, workspace_id, is_active) "
            "VALUES ('owner@due.example', 'owner', %s, 'admin', %s, TRUE)", (hash_password("a-long-test-password-1"), firm["workspace"]))
        connection.cursor().execute(
            "INSERT INTO users (email, name, password_hash, role, workspace_id, is_active) "
            "VALUES ('viewer@due.example', 'viewer', %s, 'spectator', %s, TRUE)", (hash_password("a-long-test-password-1"), firm["workspace"]))
    def sign_in(email):
        browser = TestClient(main.app)
        assert browser.post("/login", data={"email": email, "password": "a-long-test-password-1"}, follow_redirects=False).status_code in (302, 303)
        return browser
    return sign_in("owner@due.example"), sign_in("viewer@due.example")


def test_the_page_shows_the_due_day_of_every_unreceived_sale_and_flags_a_missing_one(firm):
    add_deal_sale(firm["deal"], "5000", date(2026, 11, 8), "has a day", firm["workspace"], status="expected", expected_on=date(2027, 2, 15))
    add_deal_sale(firm["deal"], "700", date(2026, 11, 8), "no day", firm["workspace"], status="expected")
    add_deal_sale(firm["deal"], "100", date(2026, 11, 8), "paid", firm["workspace"], status="collected", collected_on=date(2026, 11, 9))
    owner, _ = _browser(firm)
    page = owner.get(f"/organizations/{firm['contact']}?lang=en").text
    sales = page[page.index('id="sales"'):]
    assert "due 15.02.2027" in sales                                          # an expected sale shows its day, like booked ones
    assert sales.count("no due day yet") == 1                                 # only the undated one is flagged
    assert sales.count('/due-day"') == 2                                      # a due-day form on each unreceived sale, none on the paid one


def test_the_due_day_is_set_from_the_page(firm):
    sale = add_deal_sale(firm["deal"], "5000", date(2026, 11, 8), "", firm["workspace"], status="expected")
    owner, viewer = _browser(firm)
    path = f"/deals/{firm['deal']}/sales/{sale}/due-day"
    response = owner.post(path, data={"due_on": "15.02.2027", "next": f"/organizations/{firm['contact']}"}, follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == f"/organizations/{firm['contact']}"
    assert _rows(firm["deal"])[0]["expected_on"] == date(2027, 2, 15)
    assert owner.post(path, data={"due_on": "not a day"}, follow_redirects=False).status_code == 400
    assert owner.post(path, data={"due_on": ""}, follow_redirects=False).status_code == 400
    assert owner.post(f"/deals/{firm['deal']}/sales/999999/due-day", data={"due_on": "01.03.2027"}, follow_redirects=False).status_code == 404
    assert viewer.post(path, data={"due_on": "01.03.2027"}, follow_redirects=False).status_code == 403
    assert _rows(firm["deal"])[0]["expected_on"] == date(2027, 2, 15)
