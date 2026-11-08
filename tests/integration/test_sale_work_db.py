"""Changing the hours and the rate per hour of sales and contracts that are already entered: the new total
is spread over the payments that are still to come."""
import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

import gcrm.api.main as main
from gcrm.api.security import hash_password
from gcrm.db.connection import db
from gcrm.tools.db_organizations import save_organization
from gcrm.tools.deal_money import (
    add_deal_sale,
    set_sale_status,
    set_sale_work,
    set_series_work,
)
from gcrm.tools.deal_records import DealNotFound, get_deals
from gcrm.tools.statistics import get_sales
from gcrm.workspace_context import workspace_scope

pytestmark = pytest.mark.integration
D = Decimal
PASSWORD = "a-long-test-password-1"


def _user(workspace, email, role):
    with db() as connection:
        connection.cursor().execute(
            "INSERT INTO users (email, name, password_hash, role, workspace_id, is_active) VALUES (%s, %s, %s, %s, %s, TRUE)",
            (email, email.split("@")[0], hash_password(PASSWORD), role, workspace))


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
    _user(first, "owner@first.example", "admin")
    _user(first, "viewer@first.example", "spectator")
    with workspace_scope(first):
        org = save_organization("VHS Kaufbeuren", "Kaufbeuren", source="test_fixture")
        deal = next(d["id"] for d in get_deals("organization", org) if d["offer_slug"] == "consulting")
        contract = add_deal_sale(deal, "1200", date(2026, 11, 3), "course", first, status="booked",
                                 expected_on=date(2027, 1, 31), months=5)
        single = add_deal_sale(deal, "500", date(2026, 11, 4), "workshop", first, status="expected")
    with workspace_scope(second):
        other = save_organization("Kessler Logistik", "Ulm", source="test_fixture")
        other_deal = next(d["id"] for d in get_deals("organization", other) if d["offer_slug"] == "consulting")
    return {"first": first, "second": second, "org": org, "deal": deal, "contract": contract, "single": single, "other_deal": other_deal}


def _rows(world, description):
    with workspace_scope(world["first"]):
        return sorted((s for s in get_sales(world["org"]) if s["description"] == description), key=lambda s: s["series_part"] or 0)


def _series(world):
    return str(_rows(world, "course")[0]["series_id"])


def test_a_single_estimate_becomes_hours_at_a_rate(world):
    with workspace_scope(world["first"]):
        assert set_sale_work(world["deal"], world["single"], D("36"), D("30"), world["first"]) is True
    (sale,) = _rows(world, "workshop")
    assert (sale["amount_eur"], sale["hours"], sale["rate_eur"]) == (D("1080.00"), D("36.00"), "30.00")


def test_a_contract_is_reset_to_hours_at_a_rate_over_the_same_payments(world):
    with workspace_scope(world["first"]):
        assert set_series_work(world["deal"], _series(world), D("36"), D("30"), world["first"]) == 5
    rows = _rows(world, "course")
    assert [r["amount_eur"] for r in rows] == [D("216.00")] * 5 and [r["hours"] for r in rows] == [D("7.20")] * 5
    assert [r["expected_on"] for r in rows][0] == "2027-01-31"                        # the due days are untouched
    summary = rows[0]["contract"]
    assert (summary["total"], summary["hours"], summary["rate_eur"], summary["payments"]) == (D("1080.00"), D("36.00"), "30.00", 5)


def test_the_parts_always_add_up_to_the_hours_and_the_money(world):
    with workspace_scope(world["first"]):
        set_series_work(world["deal"], _series(world), D("1"), D("100"), world["first"])
    rows = _rows(world, "course")
    assert sum(r["amount_eur"] for r in rows) == D("100.00") and sum(r["hours"] for r in rows) == D("1.00")
    assert rows[-1]["amount_eur"] >= rows[0]["amount_eur"]                              # the odd cents land on the last payment


def test_payments_already_received_keep_their_money_and_the_rest_is_spread_over_the_open_ones(world):
    first_payment = _rows(world, "course")[0]["id"]
    with workspace_scope(world["first"]):
        set_sale_status(world["deal"], first_payment, "collected", date(2027, 2, 1), world["first"])
        assert set_series_work(world["deal"], _series(world), D("36"), D("30"), world["first"]) == 4
    rows = _rows(world, "course")
    assert rows[0]["amount_eur"] == D("240.00") and rows[0]["status"] == "collected"       # received: unchanged
    assert [r["amount_eur"] for r in rows[1:]] == [D("210.00")] * 4                          # (1080 - 240) / 4
    assert sum(r["amount_eur"] for r in rows) == D("1080.00") and sum(r["hours"] for r in rows if r["hours"]) == D("36.00")


def test_cancelled_payments_are_left_alone(world):
    rows = _rows(world, "course")
    with workspace_scope(world["first"]):
        set_sale_status(world["deal"], rows[4]["id"], "cancelled", None, world["first"])
        assert set_series_work(world["deal"], _series(world), D("36"), D("30"), world["first"]) == 4
    rows = _rows(world, "course")
    assert rows[4]["status"] == "cancelled" and rows[4]["amount_eur"] == D("240.00") and rows[4]["hours"] is None
    assert [r["amount_eur"] for r in rows[:4]] == [D("270.00")] * 4                           # 1080 over the four still counted


def test_a_total_below_what_was_already_received_is_refused_and_changes_nothing(world):
    rows = _rows(world, "course")
    with workspace_scope(world["first"]):
        for row in rows[:2]:
            set_sale_status(world["deal"], row["id"], "collected", date(2027, 2, 1), world["first"])
        with pytest.raises(ValueError):
            set_series_work(world["deal"], _series(world), D("10"), D("30"), world["first"])        # 300 < 480 received
    assert [r["amount_eur"] for r in _rows(world, "course")] == [D("240.00")] * 5


def test_nothing_changes_for_a_received_single_sale_or_a_contract_with_nothing_open(world):
    with workspace_scope(world["first"]):
        set_sale_status(world["deal"], world["single"], "collected", date(2027, 2, 1), world["first"])
        assert set_sale_work(world["deal"], world["single"], D("10"), D("30"), world["first"]) is False
        for row in _rows(world, "course"):
            set_sale_status(world["deal"], row["id"], "collected", date(2027, 2, 1), world["first"])
        with pytest.raises(ValueError):
            set_series_work(world["deal"], _series(world), D("36"), D("30"), world["first"])
    assert _rows(world, "workshop")[0]["amount_eur"] == D("500.00")


@pytest.mark.parametrize("hours,rate", [(D("0"), D("30")), (D("-1"), D("30")), (D("36"), D("0")), (D("36"), D("-5")),
                                        (None, D("30")), (D("36"), None), ("lots", D("30")), (D("100001"), D("30"))])
def test_nonsense_hours_or_rates_are_refused(world, hours, rate):
    with workspace_scope(world["first"]):
        with pytest.raises(ValueError):
            set_series_work(world["deal"], _series(world), hours, rate, world["first"])
        with pytest.raises(ValueError):
            set_sale_work(world["deal"], world["single"], hours, rate, world["first"])
    assert [r["amount_eur"] for r in _rows(world, "course")] == [D("240.00")] * 5


def test_another_workspaces_deal_and_an_unknown_contract_are_not_touched(world):
    with workspace_scope(world["first"]):
        with pytest.raises(DealNotFound):
            set_series_work(world["other_deal"], _series(world), D("36"), D("30"), world["first"])
        assert set_series_work(world["deal"], str(uuid.uuid4()), D("36"), D("30"), world["first"]) == 0
        assert set_sale_work(world["deal"], 999999, D("36"), D("30"), world["first"]) is False
    assert [r["amount_eur"] for r in _rows(world, "course")] == [D("240.00")] * 5


def _browser(email):
    browser = TestClient(main.app)
    assert browser.post("/login", data={"email": email, "password": PASSWORD}, follow_redirects=False).status_code in (302, 303)
    return browser


def test_the_page_shows_forms_for_the_contract_and_the_sale_and_they_work(world):
    admin = _browser("owner@first.example")
    page = admin.get(f"/organizations/{world['org']}?lang=en").text.replace("\xa0", " ")
    assert f"/deals/{world['deal']}/series/{_series(world)}/work" in page and f"/deals/{world['deal']}/sales/{world['single']}/work" in page
    reply = admin.post(f"/deals/{world['deal']}/series/{_series(world)}/work",
                       data={"hours": "36", "rate": "30", "next": f"/organizations/{world['org']}"}, follow_redirects=False)
    assert reply.status_code == 303
    page = admin.get(f"/organizations/{world['org']}?lang=en").text.replace("\xa0", " ")
    assert "36 h × 30 €/h" in page and "in 5 payments" in page
    assert admin.post(f"/deals/{world['deal']}/sales/{world['single']}/work", data={"hours": "10", "rate": "45,50"},
                      follow_redirects=False).status_code == 303
    assert _rows(world, "workshop")[0]["amount_eur"] == D("455.00")


def test_bad_input_is_a_400_a_missing_contract_a_404_and_a_viewer_is_refused(world):
    admin, viewer = _browser("owner@first.example"), _browser("viewer@first.example")
    url = f"/deals/{world['deal']}/series/{_series(world)}/work"
    for bad in ({"hours": "", "rate": "30"}, {"hours": "36", "rate": ""}, {"hours": "x", "rate": "30"}, {"hours": "-1", "rate": "30"}):
        assert admin.post(url, data=bad, follow_redirects=False).status_code == 400, bad
    assert admin.post(f"/deals/{world['deal']}/series/{uuid.uuid4()}/work", data={"hours": "1", "rate": "1"}, follow_redirects=False).status_code == 404
    assert admin.post(f"/deals/{world['deal']}/series/not-a-uuid/work", data={"hours": "1", "rate": "1"}, follow_redirects=False).status_code == 404
    assert admin.post(f"/deals/{world['deal']}/sales/999999/work", data={"hours": "1", "rate": "1"}, follow_redirects=False).status_code == 404
    assert admin.post(f"/deals/{world['other_deal']}/sales/{world['single']}/work", data={"hours": "1", "rate": "1"}, follow_redirects=False).status_code == 404
    assert viewer.post(url, data={"hours": "36", "rate": "30"}, follow_redirects=False).status_code == 403
    assert [r["amount_eur"] for r in _rows(world, "course")] == [D("240.00")] * 5
