"""Revenue per organization and for the whole business, by sale status, on the real schema."""
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

import gcrm.api.main as main
from gcrm.api.routers.organizations import (
    _build_organization_filters,
    _fetch_organizations_page,
    _sort_column,
)
from gcrm.db.connection import db
from gcrm.tools.db_deals import set_organization_deal
from gcrm.tools.db_organizations import save_organization
from gcrm.tools.db_people import save_person
from gcrm.tools.deal_money import add_deal_sale
from gcrm.tools.deal_records import add_deal, get_deals
from gcrm.tools.revenue import business_revenue
from gcrm.workspace_context import workspace_scope

pytestmark = pytest.mark.integration

AMOUNTS = {"expected": "100", "booked": "200", "contracted": "300", "collected": "400", "cancelled": "50"}


def _deal(owner: str, owner_id: int, slug: str) -> int:
    return next(d["id"] for d in get_deals(owner, owner_id) if d["offer_slug"] == slug)


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
    with workspace_scope(first):
        busy = save_organization("Brandt Maschinenbau", "Augsburg", source="test_fixture")
        quiet = save_organization("Quiet Gallery", "Ulm", source="test_fixture")
        gone = save_organization("Deleted Firm", "Bonn", source="test_fixture")
        consulting = _deal("organization", busy, "consulting")
        for status, amount in AMOUNTS.items():
            add_deal_sale(consulting, amount, date(2026, 11, 3), status, first, status=status,
                          collected_on=date(2026, 11, 5) if status == "collected" else None)
        with db() as connection:
            set_organization_deal(connection.cursor(), busy, stage="customer", offer="learnwohl")
        add_deal_sale(_deal("organization", busy, "learnwohl"), "1000", date(2026, 11, 3), "LW", first, status="booked")
        add_deal_sale(_deal("organization", gone, "consulting"), "777", date(2026, 11, 3), "x", first, status="collected")
        with db() as connection:
            connection.cursor().execute("UPDATE contacts SET deleted_at = NOW() WHERE id = %s", (gone,))
        solo = save_person("Pat Freelancer", source="test_fixture")
        with db() as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT offer_id_for(NULL, 'consulting') AS id")
            solo_deal = add_deal("person", solo, cursor.fetchone()["id"])
        add_deal_sale(solo_deal, "10", date(2026, 11, 3), "coaching", first, status="expected")
    with workspace_scope(second):
        other = save_organization("Kessler Logistik", "Ulm", source="test_fixture")
        add_deal_sale(_deal("organization", other, "consulting"), "99999", date(2026, 11, 3), "big", second, status="collected",
                      collected_on=date(2026, 11, 4))
    return {"first": first, "second": second, "busy": busy, "quiet": quiet}


def _rows(workspace: int, offer=None, sort_col="c.id", sort_dir="ASC"):
    where, params = _build_organization_filters("", "", "", "", "", workspace, "", "", "", offer, "")
    rows, *_ = _fetch_organizations_page(where, params, sort_col, sort_dir, 0, None, workspace, offer)
    return {row["name"]: row for row in rows}


def test_each_organization_shows_its_revenue_by_status_and_a_total_without_cancelled(world):
    rows = _rows(world["first"])
    busy = rows["Brandt Maschinenbau"]
    # consulting 100/200/300/400 (+50 cancelled) plus a 1000 booked learnwohl sale
    assert (busy["rev_expected"], busy["rev_booked"], busy["rev_contracted"], busy["rev_collected"],
            busy["rev_cancelled"]) == (Decimal("100"), Decimal("1200"), Decimal("300"), Decimal("400"), Decimal("50"))
    assert busy["rev_total"] == Decimal("2000")   # expected + booked + contracted + collected
    quiet = rows["Quiet Gallery"]
    assert (quiet["rev_total"], quiet["rev_collected"], quiet["rev_cancelled"]) == (Decimal("0"), Decimal("0"), Decimal("0"))
    assert "Kessler Logistik" not in rows and "Deleted Firm" not in rows


def test_the_offer_filter_limits_the_revenue_to_that_offer(world):
    busy = _rows(world["first"], offer="learnwohl")["Brandt Maschinenbau"]
    assert (busy["rev_booked"], busy["rev_total"], busy["rev_collected"]) == (Decimal("1000"), Decimal("1000"), Decimal("0"))


def test_the_whole_business_includes_people_but_not_other_workspaces_or_deleted_organizations(world):
    totals = business_revenue(world["first"])
    assert totals["expected"] == {"eur": Decimal("110"), "count": 2}      # 100 on the firm + 10 on the freelancer
    assert totals["booked"]["eur"] == Decimal("1200") and totals["contracted"]["eur"] == Decimal("300")
    assert totals["collected"]["eur"] == Decimal("400")                   # not Kessler's 99999, not the deleted firm's 777
    assert totals["cancelled"]["eur"] == Decimal("50")
    assert totals["total"] == Decimal("2010")
    assert business_revenue(world["second"])["collected"]["eur"] == Decimal("99999")
    assert business_revenue(world["first"], offer="learnwohl")["total"] == Decimal("1000")


def test_the_list_sorts_by_collected_and_by_total(world):
    with workspace_scope(world["first"]):
        extra = save_organization("Zed Works", "Hof", source="test_fixture")
        add_deal_sale(_deal("organization", extra, "consulting"), "5000", date(2026, 11, 3), "z", world["first"],
                      status="expected")
    by_total = list(_rows(world["first"], sort_col=_sort_column("revenue_total", None), sort_dir="DESC"))
    assert by_total[:2] == ["Zed Works", "Brandt Maschinenbau"]
    by_collected = list(_rows(world["first"], sort_col=_sort_column("revenue_collected", None), sort_dir="DESC"))
    assert by_collected[0] == "Brandt Maschinenbau"


def test_the_page_shows_the_business_strip_and_a_revenue_cell_per_row(world):
    with workspace_scope(world["first"]):
        extra = save_organization("Zed Works", "Hof", source="test_fixture")
        add_deal_sale(_deal("organization", extra, "consulting"), "5000", date(2026, 11, 3), "z", world["first"],
                      status="expected")
    from gcrm.api.security import hash_password
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("INSERT INTO users (email, name, password_hash, role, workspace_id, is_active) "
                       "VALUES ('owner@first.example', 'owner', %s, 'admin', %s, TRUE)",
                       (hash_password("a-long-test-password-1"), world["first"]))
    browser = TestClient(main.app)       # a real signed-in session, so the workspace is enforced as in production
    login = browser.post("/login", data={"email": "owner@first.example", "password": "a-long-test-password-1"},
                         follow_redirects=False)
    assert login.status_code in (302, 303)
    page = browser.get("/organizations/?lang=en&sort=revenue_total&dir=desc").text
    strip = page[page.index('class="revenue-strip"'):page.index('class="list-controls"')]
    for status, label in (("expected", "Expected"), ("booked", "Booked"), ("contracted", "Contracted"),
                          ("collected", "Collected"), ("cancelled", "Cancelled"), ("total", "Total")):
        assert f'revenue-tile revenue-tile--{status}' in strip and f'revenue-tile__label">{label}<' in strip
    assert "Revenue, whole business" in strip and "without cancelled" in strip
    assert "99.999" not in page and "99,999" not in page          # another workspace's money is nowhere on the page
    table = page[page.index('class="orgs-table"'):]
    assert table.index("Zed Works") < table.index("Brandt Maschinenbau")     # sorted by total, highest first
    busy_row = table[table.index("Brandt Maschinenbau"):]
    busy_row = busy_row[:busy_row.index("</tr>")]
    assert "revenue-col--total" in busy_row and "2.000" in busy_row.replace("\xa0", "")
