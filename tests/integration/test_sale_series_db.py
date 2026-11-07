"""A contract paid over several months, on the real schema: one row per payment, each with
its own due date, amount and status, all tied together by a series id."""
from datetime import date
from decimal import Decimal

import pytest

from gcrm.db.connection import db
from gcrm.tools.db_organizations import save_organization
from gcrm.tools.deal_money import add_deal_sale, deal_money, set_sale_status, set_series_status
from gcrm.tools.deal_records import DealNotFound, get_deals
from gcrm.tools.statistics import add_sale, get_sales, get_statistics

pytestmark = pytest.mark.integration


@pytest.fixture
def firm(clean_database, monkeypatch):
    monkeypatch.setattr("gcrm.tools.db_organizations.geocode", lambda city, country: None)
    contact = save_organization("VHS Musterstadt", "Augsburg", pipeline_stage="prospect", source="test_fixture")
    other = save_organization("Other School", "Ulm", pipeline_stage="prospect", source="test_fixture")
    deals = {c: next(d["id"] for d in get_deals("organization", c) if d["offer_slug"] == "consulting")
             for c in (contact, other)}
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug = 'default'")
        workspace = cursor.fetchone()["id"]
    return {"contact": contact, "deal": deals[contact], "other_deal": deals[other], "workspace": workspace}


def _rows(deal):
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id, amount_eur, status, won_on, expected_on, collected_on, series_id, series_part, "
                       "series_total FROM sales WHERE deal_id = %s AND deleted_at IS NULL "
                       "ORDER BY series_part NULLS FIRST, id", (deal,))
        return [dict(r) for r in cursor.fetchall()]


def _contract(firm, months=4, total="2400", status="booked", first=date(2027, 2, 1)):
    first_id = add_deal_sale(firm["deal"], total, date(2026, 11, 8), "English courses", firm["workspace"],
                             status=status, expected_on=first, months=months)
    return first_id, _rows(firm["deal"])


def test_a_contract_becomes_one_row_per_month_with_the_split_amounts_and_due_dates(firm):
    _, rows = _contract(firm)
    assert [r["amount_eur"] for r in rows] == [Decimal("600.00")] * 4
    assert [r["expected_on"] for r in rows] == [date(2027, 2, 1), date(2027, 3, 1), date(2027, 4, 1), date(2027, 5, 1)]
    assert {r["status"] for r in rows} == {"booked"} and {r["won_on"] for r in rows} == {date(2026, 11, 8)}
    assert len({r["series_id"] for r in rows}) == 1
    assert [(r["series_part"], r["series_total"]) for r in rows] == [(1, 4), (2, 4), (3, 4), (4, 4)]


def test_a_single_payment_is_an_ordinary_sale_with_no_series(firm):
    sale = add_deal_sale(firm["deal"], "500", date(2026, 11, 8), "", firm["workspace"], status="booked")
    (row,) = _rows(firm["deal"])
    assert row["id"] == sale and row["series_id"] is None and row["series_part"] is None


def test_a_schedule_needs_a_first_due_day_and_cannot_start_as_collected(firm):
    with pytest.raises(ValueError):
        add_deal_sale(firm["deal"], "900", date(2026, 11, 8), "", firm["workspace"], status="booked", months=3)
    with pytest.raises(ValueError):
        add_deal_sale(firm["deal"], "900", date(2026, 11, 8), "", firm["workspace"], status="collected",
                      expected_on=date(2027, 1, 1), months=3)
    assert _rows(firm["deal"]) == []         # a refused contract leaves no half-made rows


def test_the_pipeline_counts_every_open_payment_and_money_won_only_the_received_ones(firm):
    _, rows = _contract(firm)
    set_sale_status(firm["deal"], rows[0]["id"], "collected", collected_on=date(2027, 2, 3), workspace_id=firm["workspace"])
    feb = get_statistics(firm["workspace"], date(2027, 2, 1), date(2027, 2, 28), today=date(2027, 2, 28))
    assert feb["current"]["won_eur"] == Decimal("600.00")
    assert feb["pipeline"]["booked"]["eur"] == Decimal("1800.00")     # March, April, May still to come
    money = deal_money([firm["deal"]])[firm["deal"]]
    assert (money["sales_total"], money["pipeline_total"]) == (Decimal("600.00"), Decimal("1800.00"))
    mar = get_statistics(firm["workspace"], date(2027, 3, 1), date(2027, 3, 31), today=date(2027, 3, 31))
    assert mar["current"]["won_eur"] == Decimal("0")                  # March not received yet


def test_the_whole_contract_moves_together_but_a_received_payment_stays_received(firm):
    _, rows = _contract(firm)
    set_sale_status(firm["deal"], rows[0]["id"], "collected", collected_on=date(2027, 2, 3), workspace_id=firm["workspace"])
    series = rows[0]["series_id"]
    assert set_series_status(firm["deal"], series, "contracted", workspace_id=firm["workspace"]) == 3
    assert [r["status"] for r in _rows(firm["deal"])] == ["collected", "contracted", "contracted", "contracted"]
    assert set_series_status(firm["deal"], series, "cancelled", workspace_id=firm["workspace"]) == 3
    assert [r["status"] for r in _rows(firm["deal"])] == ["collected", "cancelled", "cancelled", "cancelled"]
    assert set_series_status(firm["deal"], series, "booked", workspace_id=firm["workspace"]) == 3   # undo
    assert [r["status"] for r in _rows(firm["deal"])] == ["collected", "booked", "booked", "booked"]


def test_the_whole_contract_cannot_be_marked_collected_in_one_go(firm):
    _, rows = _contract(firm)
    with pytest.raises(ValueError):
        set_series_status(firm["deal"], rows[0]["series_id"], "collected", workspace_id=firm["workspace"])


def test_a_series_can_only_be_changed_through_its_own_deal(firm):
    _, rows = _contract(firm)
    assert set_series_status(firm["other_deal"], rows[0]["series_id"], "cancelled", workspace_id=firm["workspace"]) == 0
    with pytest.raises(DealNotFound):
        set_series_status(999999, rows[0]["series_id"], "cancelled", workspace_id=firm["workspace"])
    assert {r["status"] for r in _rows(firm["deal"])} == {"booked"}


def test_the_organization_form_path_makes_a_schedule_too_and_the_list_keeps_it_together(firm):
    first = add_sale(firm["workspace"], firm["contact"], Decimal("3000"), date(2026, 11, 8), "Autumn course",
                     status="booked", expected_on=date(2027, 1, 15), months=3)
    assert first is not None
    listed = get_sales(firm["contact"])
    assert [(s["series_part"], s["series_total"]) for s in listed] == [(1, 3), (2, 3), (3, 3)]     # grouped, in order
    assert sum(Decimal(s["amount_eur"]) for s in listed) == Decimal("3000.00")
    with pytest.raises(ValueError):
        add_sale(firm["workspace"], firm["contact"], Decimal("3000"), date(2026, 11, 8), "", status="booked", months=3)


def test_the_page_groups_a_contract_and_the_form_asks_for_the_months(firm):
    from fastapi.testclient import TestClient

    import gcrm.api.main as main
    from gcrm.api.security import hash_password
    with db() as connection:
        connection.cursor().execute(
            "INSERT INTO users (email, name, password_hash, role, workspace_id, is_active) "
            "VALUES ('owner@vhs.example', 'owner', %s, 'admin', %s, TRUE)",
            (hash_password("a-long-test-password-1"), firm["workspace"]))
    _, rows = _contract(firm)
    browser = TestClient(main.app)
    assert browser.post("/login", data={"email": "owner@vhs.example", "password": "a-long-test-password-1"},
                        follow_redirects=False).status_code in (302, 303)
    page = browser.get(f"/organizations/{firm['contact']}?lang=en").text
    for part in (1, 2, 3, 4):
        assert f"payment {part} of 4" in page
    series = rows[0]["series_id"]
    assert page.count(f'/series/{series}/status"') == 1          # one control for the whole contract
    assert 'name="months"' in page and "monthly payments" in page
    created = browser.post(f"/organizations/{firm['contact']}/sales", follow_redirects=False, data={
        "amount_eur": "1200", "won_on": "08.11.2026", "status": "booked", "expected_on": "01.03.2027", "months": "3"})
    assert created.status_code == 303
    assert len(_rows(firm["deal"])) == 4 + 3
    refused = browser.post(f"/organizations/{firm['contact']}/sales", follow_redirects=False, data={
        "amount_eur": "1200", "won_on": "08.11.2026", "status": "booked", "months": "3"})
    assert refused.status_code == 400 and "first payment" in refused.text


def test_the_organization_form_makes_monthly_payments_of_the_typed_amount_or_one_single_sale(firm):
    from fastapi.testclient import TestClient

    import gcrm.api.main as main
    from gcrm.api.security import hash_password
    with db() as connection:
        connection.cursor().execute(
            "INSERT INTO users (email, name, password_hash, role, workspace_id, is_active) "
            "VALUES ('owner2@vhs.example', 'owner2', %s, 'admin', %s, TRUE)",
            (hash_password("a-long-test-password-1"), firm["workspace"]))
    browser = TestClient(main.app)
    assert browser.post("/login", data={"email": "owner2@vhs.example", "password": "a-long-test-password-1"},
                        follow_redirects=False).status_code in (302, 303)
    path = f"/organizations/{firm['contact']}/sales"
    base = {"won_on": "08.11.2026", "status": "booked", "expected_on": "01.03.2027"}
    assert browser.post(path, data={**base, "amount_eur": "500", "schedule": "monthly", "months": "3"},
                        follow_redirects=False).status_code == 303
    rows = _rows(firm["deal"])
    assert [r["amount_eur"] for r in rows] == [Decimal("500.00")] * 3          # 500 per month, not 500 in all
    assert [r["expected_on"] for r in rows] == [date(2027, 3, 1), date(2027, 4, 1), date(2027, 5, 1)]
    assert browser.post(path, data={**base, "amount_eur": "800", "schedule": "one", "months": "9"},
                        follow_redirects=False).status_code == 303
    assert len(_rows(firm["deal"])) == 4 and _rows(firm["deal"])[0]["series_id"] is None          # one plain sale, the months box ignored
    page = browser.get(f"/organizations/{firm['contact']}?lang=en").text
    assert 'name="schedule"' in page and "One-time payment" in page and "Paid monthly" in page


def test_the_whole_contract_control_follows_the_payments_still_to_come(firm):
    from fastapi.testclient import TestClient

    import gcrm.api.main as main
    from gcrm.api.security import hash_password
    with db() as connection:
        connection.cursor().execute(
            "INSERT INTO users (email, name, password_hash, role, workspace_id, is_active) "
            "VALUES ('owner3@vhs.example', 'owner3', %s, 'admin', %s, TRUE)",
            (hash_password("a-long-test-password-1"), firm["workspace"]))
    _, rows = _contract(firm, months=3, total="1500")
    browser = TestClient(main.app)
    assert browser.post("/login", data={"email": "owner3@vhs.example", "password": "a-long-test-password-1"},
                        follow_redirects=False).status_code in (302, 303)
    page_url = f"/organizations/{firm['contact']}?lang=en"

    def control(html):
        start = html.index("sale-contract")
        block = html[start:html.index("</li>", start)]
        selected = block[block.index("selected") - 40:block.index("selected") + 40]
        return block, selected

    block, selected = control(browser.get(page_url).text)
    assert 'value="booked" selected' in block and "3 payments" in block.replace("\xa0", " ")
    # the first payment is received: the control must now describe the remaining two, not read "expected"
    set_sale_status(firm["deal"], rows[0]["id"], "collected", collected_on=date(2027, 2, 3), workspace_id=firm["workspace"])
    block, _ = control(browser.get(page_url).text)
    assert 'value="booked" selected' in block and 'value="expected" selected' not in block and "2 still to come" in block
    # saving it as it stands must leave the open payments exactly as they were
    series = rows[0]["series_id"]
    assert browser.post(f"/deals/{firm['deal']}/series/{series}/status", data={"status": "booked", "next": "/"},
                        follow_redirects=False).status_code == 303
    assert [r["status"] for r in _rows(firm["deal"])] == ["collected", "booked", "booked"]
    # once every payment is received there is nothing left to move
    for row in rows[1:]:
        set_sale_status(firm["deal"], row["id"], "collected", collected_on=date(2027, 3, 3), workspace_id=firm["workspace"])
    assert "sale-contract" not in browser.get(page_url).text
