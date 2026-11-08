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


def _extra_sales(world):
    """A booked payment that was due on 30 October and has not arrived, and one booked sale with no due day."""
    with workspace_scope(world["first"]):
        with db() as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT d.id FROM deals d JOIN offers o ON o.id = d.offer_id JOIN contacts c ON c.id = d.contact_id "
                           "WHERE c.name = 'VHS Musterstadt' AND o.slug = 'consulting'")
            deal = cursor.fetchone()["id"]
        add_deal_sale(deal, "400", date(2026, 10, 12), "late payer", world["first"], status="booked", expected_on=date(2026, 10, 30))
        add_deal_sale(deal, "500", date(2026, 11, 12), "no date yet", world["first"], status="booked")


def _outlook(world, workspace="first", offer=None):
    return _flow(world, "outlook", workspace, offer)


def test_the_outlook_runs_monthly_from_the_first_month_to_twelve_months_ahead_and_marks_the_future(world):
    flow = _outlook(world)
    assert flow["granularity"] == "month" and flow["range"] == "outlook"
    starts = [b["start"] for b in flow["buckets"]]
    assert starts[0] == date(2026, 10, 1) and starts[-1] == date(2027, 11, 1) and len(starts) == 14
    assert [b["future"] for b in flow["buckets"]] == [False, False] + [True] * 12
    assert flow["buckets"][1]["end"] == date(2026, 11, 30)                     # a bucket keeps its true last day


def test_money_in_so_far_stops_at_today_and_the_past_months_are_unchanged(world):
    flow = _outlook(world)
    october, november, december = flow["buckets"][:3]
    assert (october["cum_money_in"], november["cum_money_in"]) == (D("2100.00"), D("3000.00"))
    assert december["cum_money_in"] is None and december["money_in"] is None and december["sales_in"] is None
    assert (october["entered_total"], november["entered_total"], december["entered_total"]) == (D("600"), D("3700"), D("0"))


def test_the_projection_adds_scheduled_sales_by_due_day_and_covering_income_to_what_is_collected(world):
    _extra_sales(world)
    flow = _outlook(world)
    projection = {b["start"]: b["projection"] for b in flow["buckets"]}
    # collected so far 600; other income 1500 a month Oct to Mar; scheduled: person 300 (28 Nov) and the late 400 -> November,
    # the contract 600 a month Feb to May, the expected 1000 in June
    assert projection[date(2026, 10, 1)] == D("2100.00")                          # the last month already behind us: what really came in
    expected = {date(2026, 11, 1): D("4300"), date(2026, 12, 1): D("5800"), date(2027, 1, 1): D("7300"), date(2027, 2, 1): D("9400"),
                date(2027, 3, 1): D("11500"), date(2027, 4, 1): D("12100"), date(2027, 5, 1): D("12700"), date(2027, 6, 1): D("13700"),
                date(2027, 11, 1): D("13700")}
    for month, value in expected.items():
        assert projection[month].quantize(D("0.01")) == value, month


def test_a_payment_past_its_due_day_is_placed_in_this_month_and_one_without_a_due_day_is_listed_apart(world):
    _extra_sales(world)
    flow = _outlook(world)
    november = flow["buckets"][1]
    assert november["proj_sales"] == D("700")                                      # 300 contracted + the late 400
    assert flow["buckets"][0]["proj_sales"] == D("0")                              # October's late payment did not stay in October
    assert (flow["undated"]["count"], flow["undated"]["total"]) == (1, D("500"))


def test_the_target_runs_on_through_every_month_ahead(world):
    flow = _outlook(world)
    target = [b["cum_target"] for b in flow["buckets"]]
    assert target[0] == D("5000.00") and target[1] == D("10000.00")               # the whole of this month, not to date
    assert target[-1] == D("70000.00") and flow["has_target"] is True


def test_the_other_income_ends_when_it_ends(world):
    flow = _outlook(world)
    covered = [b["proj_other"] for b in flow["buckets"]]
    assert [c.quantize(D("0.01")) for c in covered[:7]] == [D("1500.00")] * 6 + [D("0.00")]      # Oct to Mar


def test_another_workspace_gets_its_own_outlook_without_a_target(world):
    flow = _outlook(world, workspace="second")
    assert flow["has_target"] is False and flow["undated"] == {"count": 0, "total": D("0"), "items": []}
    assert flow["buckets"][0]["start"] == date(2026, 11, 1) and len(flow["buckets"]) == 13
    assert flow["buckets"][0]["cum_money_in"] == D("99999.00") and flow["buckets"][-1]["projection"] == D("99999.00")
    assert "Brandt" not in str(_outlook(world)) and "Kessler" not in str(_outlook(world))


def test_the_offer_filter_removes_the_sales_but_not_the_other_income(world):
    _extra_sales(world)
    flow = _outlook(world, offer="learnwohl")
    assert all(b["proj_sales"] == D("0") for b in flow["buckets"]) and flow["undated"]["count"] == 0
    assert flow["buckets"][-1]["projection"].quantize(D("0.01")) == D("9000.00")        # six months of 1500, nothing else


def test_the_sales_with_no_due_day_are_listed_with_who_they_belong_to_so_they_can_be_fixed(world):
    with workspace_scope(world["first"]):
        with db() as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT d.id AS deal, c.id AS contact FROM deals d JOIN offers o ON o.id = d.offer_id "
                           "JOIN contacts c ON c.id = d.contact_id WHERE c.name = 'VHS Musterstadt' AND o.slug = 'consulting'")
            org = cursor.fetchone()
            cursor.execute("SELECT d.id AS deal, p.id AS person FROM deals d JOIN people p ON p.id = d.person_id "
                           "WHERE p.name = 'Pat Freelancer'")
            person = cursor.fetchone()
        first = add_deal_sale(org["deal"], "800", date(2026, 11, 9), "Eckert", world["first"], status="expected")
        second = add_deal_sale(person["deal"], "250", date(2026, 11, 10), "coaching", world["first"], status="booked")
    flow = _outlook(world)
    items = flow["undated"]["items"]
    assert (flow["undated"]["count"], flow["undated"]["total"]) == (2, D("1050"))
    assert [(i["sale_id"], i["status"], i["amount_eur"]) for i in items] == [(first, "expected", D("800")), (second, "booked", D("250"))]
    assert items[0]["organization_id"] == org["contact"] and items[0]["organization_name"] == "VHS Musterstadt" and items[0]["person_id"] is None
    assert items[1]["person_id"] == person["person"] and items[1]["person_name"] == "Pat Freelancer" and items[1]["organization_id"] is None
    assert items[0]["deal_id"] == org["deal"] and items[0]["description"] == "Eckert"


def test_giving_an_undated_expected_sale_a_day_brings_it_into_the_projection(world):
    from gcrm.tools.deal_money import set_sale_due_day
    with workspace_scope(world["first"]):
        with db() as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT d.id AS deal FROM deals d JOIN offers o ON o.id = d.offer_id JOIN contacts c ON c.id = d.contact_id "
                           "WHERE c.name = 'VHS Musterstadt' AND o.slug = 'consulting'")
            deal = cursor.fetchone()["deal"]
        sale = add_deal_sale(deal, "800", date(2026, 11, 9), "Eckert", world["first"], status="expected")
    before = _outlook(world)
    assert before["undated"]["count"] == 1 and before["undated"]["items"][0]["sale_id"] == sale
    with workspace_scope(world["first"]):
        assert set_sale_due_day(deal, sale, date(2027, 3, 10), world["first"]) == 1
    after = _outlook(world)
    assert after["undated"] == {"count": 0, "total": D("0"), "items": []}
    march = next(b for b in after["buckets"] if b["start"] == date(2027, 3, 1))
    march_before = next(b for b in before["buckets"] if b["start"] == date(2027, 3, 1))
    assert march["projection"] - march_before["projection"] == D("800")
    assert after["buckets"][-1]["projection"] - before["buckets"][-1]["projection"] == D("800")
    assert next(b for b in after["buckets"] if b["start"] == date(2027, 2, 1))["projection"] == \
        next(b for b in before["buckets"] if b["start"] == date(2027, 2, 1))["projection"]        # nothing earlier than its month moved
