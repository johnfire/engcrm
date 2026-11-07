"""The forecast on the real schema: money placed by month, quarter and year, against targets."""
from datetime import date
from decimal import Decimal

import pytest

from gcrm.db.connection import db
from gcrm.tools.db_organizations import save_organization
from gcrm.tools.db_people import save_person
from gcrm.tools.deal_money import add_deal_sale, set_sale_status
from gcrm.tools.deal_records import add_deal, get_deals
from gcrm.tools.forecast import get_forecast
from gcrm.tools.income_plan import (
    add_other_income,
    delete_other_income,
    get_plan,
    save_monthly_need,
    set_other_income_confirmed,
)
from gcrm.workspace_context import workspace_scope

pytestmark = pytest.mark.integration
D = Decimal
TODAY = date(2026, 11, 17)


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
        deal = _deal("organization", school)
        # a collected one-off in November, a 4-month contract from February, an expected one in June,
        # an undated booked one, a cancelled one, and one more in a different offer
        add_deal_sale(deal, "600", date(2026, 11, 2), "Workshop", first, status="collected", collected_on=date(2026, 11, 5))
        add_deal_sale(deal, "2400", date(2026, 11, 8), "Courses", first, status="booked",
                      expected_on=date(2027, 2, 1), months=4)
        add_deal_sale(deal, "1000", date(2026, 11, 8), "Maybe", first, status="expected", expected_on=date(2027, 6, 10))
        add_deal_sale(deal, "700", date(2026, 11, 8), "No date yet", first, status="booked")
        lost = add_deal_sale(deal, "900", date(2026, 11, 8), "Fell through", first, status="booked", expected_on=date(2026, 12, 1))
        set_sale_status(deal, lost, "cancelled", workspace_id=first)
        with db() as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT offer_id_for(NULL, 'consulting') AS id")
            solo = save_person("Pat Freelancer", source="test_fixture")
            own = add_deal("person", solo, cursor.fetchone()["id"])
        add_deal_sale(own, "300", date(2026, 11, 8), "Coaching", first, status="contracted", expected_on=date(2026, 11, 28))
        save_monthly_need(D("5000"))
    with workspace_scope(second):
        other = save_organization("Kessler Logistik", "Ulm", source="test_fixture")
        add_deal_sale(_deal("organization", other), "99999", date(2026, 11, 8), "big", second, status="booked",
                      expected_on=date(2026, 11, 20))
    return {"first": first, "second": second, "deal": deal}


def _forecast(world, granularity="month", workspace="first", offer=None):
    with workspace_scope(world[workspace]):
        return get_forecast(world[workspace], granularity, TODAY, offer)


def _period(result, start):
    return next(p for p in result["periods"] if p["start"] == start)


def test_months_hold_money_on_their_due_day_and_received_money_on_the_day_it_came_in(world):
    f = _forecast(world)
    nov = _period(f, date(2026, 11, 1))
    assert (nov["collected"], nov["contracted"], nov["booked"], nov["expected"]) == (D("600"), D("300"), D("0"), D("0"))
    for month in (2, 3, 4, 5):
        p = _period(f, date(2027, month, 1))
        assert p["booked"] == D("600.00") and p["total"] == D("600.00")
    assert _period(f, date(2027, 6, 1))["expected"] == D("1000")
    assert _period(f, date(2026, 12, 1))["total"] == D("0")           # the cancelled one is nowhere


def test_money_with_no_due_day_is_kept_apart_and_never_lost(world):
    undated = _forecast(world)["undated"]
    assert (undated["booked"], undated["count"], undated["total"]) == (D("700"), 1, D("700"))


def test_secured_is_collected_plus_contracted_plus_booked_and_total_adds_expected(world):
    june = _period(_forecast(world), date(2027, 6, 1))
    assert (june["secured"], june["total"]) == (D("0"), D("1000"))
    nov = _period(_forecast(world), date(2026, 11, 1))
    assert (nov["secured"], nov["total"]) == (D("900"), D("900"))


def test_targets_come_from_the_plan_and_gaps_say_what_is_still_missing(world):
    with workspace_scope(world["first"]):
        add_other_income("Support payment", D("1500"), date(2026, 11, 1), 6, True)
        add_other_income("Possible follow-on", D("300"), date(2027, 5, 1), 15, False)
    f = _forecast(world)
    nov = _period(f, date(2026, 11, 1))
    assert nov["target"] == D("3500") and nov["gap_secured"] == D("2600") and nov["gap_total"] == D("2600")
    may = _period(f, date(2027, 5, 1))
    assert may["target"] == D("5000") and may["possible_income"] == D("300")
    assert may["gap_secured"] == D("4400")                            # 5000 target - 600 booked


def test_the_quarter_and_year_views_sum_their_months_and_their_targets(world):
    with workspace_scope(world["first"]):
        add_other_income("Support payment", D("1500"), date(2026, 11, 1), 6, True)
    q4 = _period(_forecast(world, "quarter"), date(2026, 10, 1))
    assert q4["target"] == D("5000") + D("3500") + D("3500")          # Oct, Nov, Dec
    q1 = _period(_forecast(world, "quarter"), date(2027, 1, 1))
    assert q1["booked"] == D("1200.00") and q1["target"] == D("3500") * 3
    year = _period(_forecast(world, "year"), date(2026, 1, 1))
    assert year["collected"] == D("600") and year["contracted"] == D("300")
    assert year["target"] == D("5000") * 10 + D("3500") * 2           # Jan-Oct 5000 each, Nov and Dec 3500


def test_the_tiles_are_this_month_this_quarter_and_this_year(world):
    tiles = _forecast(world)["tiles"]
    assert tiles["month"]["start"] == date(2026, 11, 1)
    assert tiles["quarter"]["start"] == date(2026, 10, 1) and tiles["year"]["start"] == date(2026, 1, 1)
    assert tiles["quarter"]["collected"] == D("600") and tiles["year"]["secured"] == D("900") and tiles["quarter"]["secured"] == D("900")


def test_no_plan_means_no_target_but_the_money_still_shows(world):
    with workspace_scope(world["second"]):
        month = _period(get_forecast(world["second"], "month", TODAY, None), date(2026, 11, 1))
    assert month["target"] is None and month["gap_secured"] is None and month["booked"] == D("99999")


def test_another_workspaces_money_and_plan_never_appear(world):
    f = _forecast(world)
    assert all(p["total"] < D("99999") for p in f["periods"]) and "99999" not in str(f)
    assert _forecast(world, workspace="second")["plan"]["monthly_need"] is None


def test_the_offer_filter_limits_the_forecast_to_that_offer(world):
    f = _forecast(world, offer="learnwohl")
    assert all(p["total"] == D("0") for p in f["periods"]) and f["undated"]["total"] == D("0")


def test_other_income_can_be_confirmed_and_removed(world):
    with workspace_scope(world["first"]):
        line = add_other_income("Possible follow-on", D("300"), date(2027, 5, 1), 15, False)
        assert get_plan()["other_income"][0]["confirmed"] is False
        assert set_other_income_confirmed(line, True)
        assert get_plan()["other_income"][0]["confirmed"] is True
        assert delete_other_income(line) and get_plan()["other_income"] == []
        assert not delete_other_income(line)
    with workspace_scope(world["second"]):
        assert not delete_other_income(line)                          # not theirs


@pytest.mark.parametrize("args", [("", D("100"), date(2026, 11, 1), 3, True), ("x", D("0"), date(2026, 11, 1), 3, True),
                                  ("x", D("100"), date(2026, 11, 1), 0, True), ("x", D("100"), date(2026, 11, 1), 121, True)])
def test_nonsense_other_income_is_refused(world, args):
    with workspace_scope(world["first"]), pytest.raises(ValueError):
        add_other_income(*args)


def test_a_negative_need_is_refused(world):
    with workspace_scope(world["first"]), pytest.raises(ValueError):
        save_monthly_need(D("-1"))
