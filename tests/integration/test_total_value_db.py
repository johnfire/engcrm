"""TV, total value: everything an organization or person is worth in sales that has not
fallen through — expected + booked + contracted + collected — on the Contacts page and at the
top of the organization and person pages."""
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

import gcrm.api.main as main
from gcrm.api.security import hash_password
from gcrm.db.connection import db
from gcrm.tools.db_contact_feed import get_contact_feed
from gcrm.tools.db_organizations import save_organization
from gcrm.tools.db_people import save_person
from gcrm.tools.deal_money import add_deal_sale, set_sale_status
from gcrm.tools.deal_records import add_deal, get_deals
from gcrm.tools.revenue import owner_total_value
from gcrm.workspace_context import workspace_scope

pytestmark = pytest.mark.integration
D = Decimal
PASSWORD = "a-long-test-password-1"


def _deal(owner, owner_id, slug="consulting"):
    return next(d["id"] for d in get_deals(owner, owner_id) if d["offer_slug"] == slug)


def _contacted(deal_id):
    with db() as connection:
        connection.cursor().execute("UPDATE deals SET status = 'contacted' WHERE id = %s", (deal_id,))


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
        cursor.execute("INSERT INTO users (email, name, password_hash, role, workspace_id, is_active) "
                       "VALUES ('owner@first.example', 'owner', %s, 'admin', %s, TRUE)", (hash_password(PASSWORD), first))
    with workspace_scope(first):
        busy = save_organization("Brandt Maschinenbau", "Augsburg", source="test_fixture")
        quiet = save_organization("Quiet Gallery", "Ulm", source="test_fixture")
        deal = _deal("organization", busy)
        for status, amount in (("expected", "100"), ("booked", "200"), ("contracted", "300"), ("collected", "400"), ("cancelled", "50")):
            add_deal_sale(deal, amount, date(2026, 11, 3), status, first, status=status,
                          collected_on=date(2026, 11, 5) if status == "collected" else None)
        set_sale_status(deal, add_deal_sale(deal, "1000", date(2026, 11, 3), "lw", first, status="booked"), "cancelled", workspace_id=first)
        _contacted(deal)
        _contacted(_deal("organization", quiet))
        solo = save_person("Pat Freelancer", source="test_fixture")
        with db() as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT offer_id_for(NULL, 'consulting') AS id")
            own = add_deal("person", solo, cursor.fetchone()["id"])
        add_deal_sale(own, "250", date(2026, 11, 3), "coaching", first, status="booked")
        _contacted(own)
    with workspace_scope(second):
        other = save_organization("Kessler Logistik", "Ulm", source="test_fixture")
        add_deal_sale(_deal("organization", other), "99999", date(2026, 11, 3), "big", second, status="collected",
                      collected_on=date(2026, 11, 4))
        _contacted(_deal("organization", other))
    return {"first": first, "second": second, "busy": busy, "quiet": quiet, "solo": solo}


def _feed(world, workspace="first", **kw):
    with workspace_scope(world[workspace]):
        rows = get_contact_feed(workspace_id=world[workspace], offer=None, **kw)
    return {row["name"]: row for row in rows}


def test_total_value_is_everything_not_cancelled(world):
    with workspace_scope(world["first"]):
        assert owner_total_value("organization", world["busy"])["total"] == D("1000")
        shown = owner_total_value("organization", world["busy"])
        assert (shown["expected"], shown["booked"], shown["contracted"], shown["collected"]) == (D("100"), D("200"), D("300"), D("400"))
        assert owner_total_value("organization", world["quiet"])["total"] == D("0")
        assert owner_total_value("person", world["solo"])["total"] == D("250")


def test_total_value_never_mixes_organizations_and_people_or_workspaces(world):
    with workspace_scope(world["second"]):
        assert owner_total_value("organization", world["busy"])["total"] == D("0")     # not this workspace's record
    with pytest.raises(ValueError):
        owner_total_value("company", 1)


def test_the_contacts_page_rows_carry_tv_for_organizations_and_people(world):
    rows = _feed(world)
    assert D(rows["Brandt Maschinenbau"]["total_value"]) == D("1000")
    assert D(rows["Quiet Gallery"]["total_value"]) == D("0")
    assert D(rows["Pat Freelancer"]["total_value"]) == D("250")
    assert "Kessler Logistik" not in rows


def test_the_contacts_page_can_sort_by_tv_highest_first(world):
    with workspace_scope(world["first"]):
        names = [r["name"] for r in get_contact_feed(workspace_id=world["first"], offer=None, sort="total_value", dir="desc")]
    assert names == ["Brandt Maschinenbau", "Pat Freelancer", "Quiet Gallery"]
    with workspace_scope(world["first"]):
        default = [r["name"] for r in get_contact_feed(workspace_id=world["first"], offer=None, sort="total_value")]
    assert default == names                                    # TV starts highest first, like the other value columns


def test_the_offer_filter_limits_tv_to_that_offer(world):
    with workspace_scope(world["first"]):
        rows = {r["name"]: r for r in get_contact_feed(workspace_id=world["first"], offer="learnwohl")}
    assert all(D(r["total_value"]) == 0 for r in rows.values())


def _browser():
    browser = TestClient(main.app)
    assert browser.post("/login", data={"email": "owner@first.example", "password": PASSWORD}, follow_redirects=False).status_code in (302, 303)
    return browser


def test_the_contacts_page_has_a_tv_column_between_city_and_priority(world):
    page = _browser().get("/contact-feed/?lang=en&offer=all").text
    header = page[page.index("<thead>"):page.index("</thead>")]
    assert header.index("City") < header.index(">TV") < header.index("Priority")
    row = page[page.index("Brandt Maschinenbau"):]
    assert "1.000" in row[:row.index("</tr>")].replace("\xa0", "")
    assert "99.999" not in page.replace("\xa0", "")


def test_the_organization_and_person_pages_show_tv_near_the_top(world):
    browser = _browser()
    org = browser.get(f"/organizations/{world['busy']}?lang=en").text.replace("\xa0", " ")
    assert "Total value" in org and "1.000" in org
    assert org.index("Total value") < org.index('id="sales"')              # above the Sales card, near the top
    person = browser.get(f"/people/{world['solo']}?lang=en").text.replace("\xa0", " ")
    assert "Total value" in person and "250" in person
    assert "Collected" in org and "Booked" in org and "Expected" in org      # the split behind the total
