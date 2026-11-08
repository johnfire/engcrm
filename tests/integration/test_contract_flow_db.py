"""Contract flow on the real schema: what was entered when, the running total, and money in against the
target, per week, month or year — for the right workspace only."""
from datetime import date
from decimal import Decimal

import pytest

from gcrm.db.connection import db
from gcrm.tools.contract_flow import get_contract_flow
from gcrm.tools.db_organizations import save_organization
from gcrm.tools.db_people import save_person
from gcrm.tools.deal_money import add_deal_sale, set_sale_status
from gcrm.tools.deal_records import add_deal, get_deals
from gcrm.tools.income_plan import add_other_income, save_monthly_need
from gcrm.workspace_context import workspace_scope

pytestmark = pytest.mark.integration
D = Decimal
TODAY = date(2026, 11, 18)


def _deal(owner, owner_id, slug="consulting"):
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
        school = save_organization("VHS Musterstadt", "Augsburg", source="test_fixture")
        gone = save_organization("Deleted Firm", "Bonn", source="test_fixture")
        deal = _deal("organization", school)
        add_deal_sale(deal, "100", date(2026, 8, 20), "before the business", first, status="collected", collected_on=date(2026, 8, 25))
        add_deal_sale(deal, "600", date(2026, 10, 5), "first job", first, status="collected", collected_on=date(2026, 10, 20))
        add_deal_sale(deal, "2400", date(2026, 11, 3), "courses", first, status="booked", expected_on=date(2027, 2, 1), months=4)
        add_deal_sale(deal, "1000", date(2026, 11, 10), "maybe", first, status="expected", expected_on=date(2027, 6, 1))
        lost = add_deal_sale(deal, "900", date(2026, 11, 2), "fell through", first, status="booked")
        set_sale_status(deal, lost, "cancelled", workspace_id=first)
        solo = save_person("Pat Freelancer", source="test_fixture")
        with db() as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT offer_id_for(NULL, 'consulting') AS id")
            own = add_deal("person", solo, cursor.fetchone()["id"])
        add_deal_sale(own, "300", date(2026, 11, 12), "coaching", first, status="contracted", expected_on=date(2026, 11, 28))
        add_deal_sale(_deal("organization", gone), "777", date(2026, 11, 6), "x", first, status="collected", collected_on=date(2026, 11, 7))
        with db() as connection:
            connection.cursor().execute("UPDATE contacts SET deleted_at = NOW() WHERE id = %s", (gone,))
        save_monthly_need(D("5000"), start_month=date(2026, 10, 1))
        add_other_income("Support payment", D("1500"), date(2026, 11, 1), 6, True, covers_from=date(2026, 10, 1))
    with workspace_scope(second):
        other = save_organization("Kessler Logistik", "Ulm", source="test_fixture")
        add_deal_sale(_deal("organization", other), "99999", date(2026, 11, 4), "big", second, status="collected",
                      collected_on=date(2026, 11, 5))
    return {"first": first, "second": second}


def _flow(world, range_key="all", workspace="first", offer=None):
    with workspace_scope(world[workspace]):
        return get_contract_flow(world[workspace], range_key, TODAY, offer)


def _bucket(flow, start):
    return next(b for b in flow["buckets"] if b["start"] == start)


def test_the_whole_business_by_month_counts_expected_and_everything_above_it_and_not_cancelled(world):
    flow = _flow(world)
    assert flow["granularity"] == "month" and [b["start"] for b in flow["buckets"]] == [date(2026, 10, 1), date(2026, 11, 1)]
    october, november = flow["buckets"]
    assert october["entered"]["collected"] == D("600") and october["entered_total"] == D("600") and october["deals"] == 1
    assert (november["entered"]["booked"], november["entered"]["expected"], november["entered"]["contracted"]) == \
        (D("2400"), D("1000"), D("300"))
    assert november["entered_total"] == D("3700")          # the 900 that fell through, the other workspace and the deleted firm are not here
    assert november["deals"] == 3                          # the four monthly payments are one contract: one deal


def test_the_running_total_starts_from_everything_entered_before_the_window(world):
    october, november = _flow(world)["buckets"]
    assert october["cumulative"] == D("700") and november["cumulative"] == D("4400")      # 100 was won in August


def test_three_months_is_weekly_and_the_running_total_still_includes_older_sales(world):
    flow = _flow(world, "3m")
    assert flow["granularity"] == "week" and len(flow["buckets"]) == 13 and flow["buckets"][0]["start"] == date(2026, 8, 24)
    assert _bucket(flow, date(2026, 10, 5))["entered_total"] == D("600")
    assert (_bucket(flow, date(2026, 11, 2))["entered_total"], _bucket(flow, date(2026, 11, 2))["deals"]) == (D("2400"), 1)
    assert (_bucket(flow, date(2026, 11, 9))["entered_total"], _bucket(flow, date(2026, 11, 9))["deals"]) == (D("1300"), 2)
    assert flow["buckets"][0]["cumulative"] == D("100")                   # the August sale sits in its own week
    assert flow["buckets"][-1]["cumulative"] == D("4400")


def test_a_year_is_twelve_months(world):
    flow = _flow(world, "year")
    assert flow["granularity"] == "month" and len(flow["buckets"]) == 12
    assert flow["buckets"][0]["start"] == date(2025, 12, 1) and flow["buckets"][-1]["cumulative"] == D("4400")


def test_money_in_is_collected_sales_plus_the_other_income_covering_each_period_against_the_target_pace(world):
    flow = _flow(world)
    october, november = flow["buckets"]
    assert flow["has_target"] is True
    assert (october["sales_in"], october["other_in"], october["money_in"]) == (D("600"), D("1500.00"), D("2100.00"))
    assert october["target"].quantize(D("0.01")) == D("5000.00")
    # November only up to today, the 18th: 18 of 30 days
    assert november["sales_in"] == D("0") and november["other_in"].quantize(D("0.01")) == D("900.00")
    assert november["target"].quantize(D("0.01")) == D("3000.00")
    assert november["cum_money_in"].quantize(D("0.01")) == D("3000.00") and november["cum_target"].quantize(D("0.01")) == D("8000.00")


def test_three_months_money_in_adds_up_the_same_way_week_by_week(world):
    last = _flow(world, "3m")["buckets"][-1]
    assert last["cum_money_in"].quantize(D("0.01")) == D("3100.00")        # 100 + 600 collected, 1500 + 900 other income
    assert last["cum_target"].quantize(D("0.01")) == D("8000.00")          # nothing before the business started


def test_the_offer_filter_limits_the_sales_but_not_the_plan(world):
    flow = _flow(world, offer="learnwohl")
    assert all(b["entered_total"] == D("0") and b["cumulative"] == D("0") for b in flow["buckets"])
    assert flow["buckets"][0]["other_in"].quantize(D("0.01")) == D("1500.00") and flow["has_target"] is True


def test_another_workspace_sees_only_its_own_money_and_no_target_without_a_plan(world):
    flow = _flow(world, workspace="second")
    assert flow["has_target"] is False
    (only,) = flow["buckets"]                                              # no plan, no sales before November: just this month
    assert only["entered_total"] == D("99999") and only["sales_in"] == D("99999") and only["target"] == D("0")
    assert "99999" not in str(_flow(world)) and "Kessler" not in str(_flow(world))


def test_an_unknown_range_is_refused(world):
    with workspace_scope(world["first"]), pytest.raises(ValueError):
        get_contract_flow(world["first"], "decade", TODAY, None)
