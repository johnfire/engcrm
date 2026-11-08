"""Hours of work on a sale: entered with an amount or with a rate per hour, kept per payment,
shown on the organization page, and exported."""
import io
import zipfile
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

import gcrm.api.main as main
from gcrm.api.security import hash_password
from gcrm.backup_export import build_backup
from gcrm.db.connection import db
from gcrm.tools.db_organizations import save_organization
from gcrm.tools.deal_money import add_deal_sale, deal_money
from gcrm.tools.deal_records import get_deals
from gcrm.tools.statistics import add_sale, get_sales
from gcrm.workspace_context import workspace_scope

pytestmark = pytest.mark.integration
D = Decimal
PASSWORD = "a-long-test-password-1"


@pytest.fixture
def world(clean_database, monkeypatch):
    monkeypatch.setattr("gcrm.tools.db_organizations.geocode", lambda city, country: None)
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug = 'default'")
        ws = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO users (email, name, password_hash, role, workspace_id, is_active) "
                       "VALUES ('owner@first.example', 'owner', %s, 'admin', %s, TRUE)", (hash_password(PASSWORD), ws))
    with workspace_scope(ws):
        org = save_organization("Brandt Maschinenbau", "Augsburg", source="test_fixture")
        deal = next(d["id"] for d in get_deals("organization", org) if d["offer_slug"] == "consulting")
    return {"ws": ws, "org": org, "deal": deal}


def _sales(world):
    with workspace_scope(world["ws"]):
        return get_sales(world["org"])


def test_a_sale_with_hours_and_a_rate_gets_its_amount_from_them(world):
    with workspace_scope(world["ws"]):
        add_deal_sale(world["deal"], None, date(2026, 11, 3), "course", world["ws"], status="booked", hours=D("5"), rate=D("29"))
    (sale,) = _sales(world)
    assert (sale["amount_eur"], sale["hours"]) == (D("145.00"), D("5.00"))


def test_a_sale_with_an_amount_and_hours_keeps_both_and_a_plain_sale_has_no_hours(world):
    with workspace_scope(world["ws"]):
        add_deal_sale(world["deal"], "300", date(2026, 11, 3), "workshop", world["ws"], status="booked", hours=D("12.5"))
        add_deal_sale(world["deal"], "100", date(2026, 11, 4), "advice", world["ws"], status="booked")
    by_text = {s["description"]: s for s in _sales(world)}
    assert by_text["workshop"]["hours"] == D("12.50") and by_text["advice"]["hours"] is None


def test_the_hours_of_a_monthly_contract_are_split_like_the_money(world):
    with workspace_scope(world["ws"]):
        add_deal_sale(world["deal"], "1200", date(2026, 11, 3), "course", world["ws"], status="booked",
                      expected_on=date(2027, 1, 31), months=3, hours=D("40"))
    rows = sorted(_sales(world), key=lambda s: s["series_part"])
    assert [r["hours"] for r in rows] == [D("13.33"), D("13.33"), D("13.34")]
    assert sum(r["amount_eur"] for r in rows) == D("1200") and sum(r["hours"] for r in rows) == D("40")


def test_deal_money_returns_the_hours_too(world):
    with workspace_scope(world["ws"]):
        add_deal_sale(world["deal"], "300", date(2026, 11, 3), "x", world["ws"], status="booked", hours=D("12"))
        assert deal_money([world["deal"]])[world["deal"]]["sales"][0]["hours"] == D("12.00")


def test_the_organization_route_add_sale_takes_hours_and_a_rate(world):
    with workspace_scope(world["ws"]):
        sale = add_sale(world["ws"], world["org"], None, date(2026, 11, 3), "audit", status="booked", hours=D("8"), rate=D("90"))
    assert sale is not None
    (row,) = _sales(world)
    assert (row["amount_eur"], row["hours"]) == (D("720.00"), D("8.00"))
    with workspace_scope(world["ws"]), pytest.raises(ValueError):
        add_sale(world["ws"], world["org"], D("0"), date(2026, 11, 3), "bad")


def test_the_forms_take_hours_and_a_rate_and_the_page_shows_them_with_a_total(world):
    browser = TestClient(main.app)
    assert browser.post("/login", data={"email": "owner@first.example", "password": PASSWORD}, follow_redirects=False).status_code in (302, 303)
    base = {"won_on": "03.11.2026", "status": "booked", "schedule": "one", "description": "course"}
    assert browser.post(f"/organizations/{world['org']}/sales", data={**base, "amount_eur": "", "hours": "5", "rate": "29"},
                        follow_redirects=False).status_code in (302, 303)
    monthly = {**base, "schedule": "monthly", "months": "3", "expected_on": "01.12.2026", "description": "coaching"}
    assert browser.post(f"/organizations/{world['org']}/sales", data={**monthly, "amount_eur": "", "hours": "4", "rate": "50"},
                        follow_redirects=False).status_code in (302, 303)          # 4 h and 200 euros per month, for 3 months
    rows = {s["description"]: s for s in _sales(world)}
    assert (rows["course"]["amount_eur"], rows["course"]["hours"]) == (D("145.00"), D("5.00"))
    coaching = [s for s in _sales(world) if s["description"] == "coaching"]
    assert len(coaching) == 3 and all((s["amount_eur"], s["hours"]) == (D("200.00"), D("4.00")) for s in coaching)
    page = browser.get(f"/organizations/{world['org']}?lang=en").text.replace("\xa0", " ")
    assert "5 h" in page and "29 €/h" in page and "17 h booked" in page                  # 5 + 3 x 4
    for bad in ({"amount_eur": "", "hours": "", "rate": ""}, {"amount_eur": "", "hours": "5", "rate": ""},
                {"amount_eur": "100", "hours": "-3", "rate": ""}, {"amount_eur": "", "hours": "x", "rate": "29"}):
        assert browser.post(f"/organizations/{world['org']}/sales", data={**base, **bad}, follow_redirects=False).status_code == 400, bad
    deal_form = browser.post(f"/deals/{world['deal']}/sales", data={**base, "amount_eur": "", "hours": "2", "rate": "100", "description": "viaDeal"},
                             follow_redirects=False)
    assert deal_form.status_code in (302, 303)
    assert [s["hours"] for s in _sales(world) if s["description"] == "viaDeal"] == [D("2.00")]


def test_cancelled_sales_do_not_count_toward_the_hours_booked(world):
    with workspace_scope(world["ws"]):
        add_deal_sale(world["deal"], "300", date(2026, 11, 3), "kept", world["ws"], status="booked", hours=D("6"))
        add_deal_sale(world["deal"], "300", date(2026, 11, 3), "gone", world["ws"], status="cancelled", hours=D("50"))
    browser = TestClient(main.app)
    browser.post("/login", data={"email": "owner@first.example", "password": PASSWORD}, follow_redirects=False)
    page = browser.get(f"/organizations/{world['org']}?lang=en").text
    assert "6 h booked" in page and "56 h" not in page


def test_the_backup_has_the_hours(world):
    with workspace_scope(world["ws"]):
        add_deal_sale(world["deal"], "300", date(2026, 11, 3), "x", world["ws"], status="booked", hours=D("12"))
    archive, _ = build_backup(world["ws"])
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        header = z.read("sales.csv").decode("utf-8-sig").splitlines()[0].split(",")
        assert "hours" in header and "12.00" in z.read("sales.csv").decode("utf-8-sig")


def test_the_forms_take_a_work_window_and_every_payment_of_a_contract_gets_it(world):
    browser = TestClient(main.app)
    browser.post("/login", data={"email": "owner@first.example", "password": PASSWORD}, follow_redirects=False)
    base = {"won_on": "03.11.2026", "status": "booked", "schedule": "monthly", "months": "3", "expected_on": "01.12.2026",
            "description": "coaching", "amount_eur": "", "hours": "4", "rate": "50"}
    assert browser.post(f"/organizations/{world['org']}/sales", data={**base, "work_from": "05.12.2026", "work_to": "28.02.2027"},
                        follow_redirects=False).status_code in (302, 303)
    rows = _sales(world)
    assert len(rows) == 3 and {(str(r["work_from"]), str(r["work_to"])) for r in rows} == {("2026-12-05", "2027-02-28")}
    for bad in ({"work_from": "05.12.2026", "work_to": ""}, {"work_from": "", "work_to": "05.12.2026"},
                {"work_from": "05.12.2026", "work_to": "01.12.2026"}):
        assert browser.post(f"/organizations/{world['org']}/sales", data={**base, **bad}, follow_redirects=False).status_code == 400, bad
    assert len(_sales(world)) == 3
    via_deal = browser.post(f"/deals/{world['deal']}/sales", data={**base, "description": "viaDeal", "schedule": "one", "work_from": "01.03.2027",
                                                                    "work_to": "31.03.2027"}, follow_redirects=False)
    assert via_deal.status_code in (302, 303)
    assert [str(s["work_from"]) for s in _sales(world) if s["description"] == "viaDeal"] == ["2027-03-01"]
