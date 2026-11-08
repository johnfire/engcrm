"""Hours booked per week: from the sales' hours (spread over their work window, or the month the payment is
due) plus, in blue, the hours of the new bookings the plan expects."""
from datetime import date
from decimal import Decimal

import pytest

from gcrm.db.connection import db
from gcrm.tools.db_organizations import save_organization
from gcrm.tools.db_people import save_person
from gcrm.tools.deal_money import add_deal_sale
from gcrm.tools.deal_records import add_deal, get_deals
from gcrm.tools.income_plan import get_plan, save_expected_new_hours, save_weekly_capacity
from gcrm.tools.weekly_hours import get_weekly_hours
from gcrm.workspace_context import workspace_scope

pytestmark = pytest.mark.integration
D = Decimal
TODAY = date(2026, 11, 11)              # a Wednesday; this week starts Monday 9 November


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
        org = save_organization("VHS Kaufbeuren", "Kaufbeuren", source="test_fixture")
        deal = next(d["id"] for d in get_deals("organization", org) if d["offer_slug"] == "consulting")
    with workspace_scope(second):
        other = save_organization("Kessler Logistik", "Ulm", source="test_fixture")
        other_deal = next(d["id"] for d in get_deals("organization", other) if d["offer_slug"] == "consulting")
        add_deal_sale(other_deal, "100", date(2026, 11, 1), "theirs", second, status="booked", hours=D("500"),
                      work_from=date(2026, 11, 9), work_to=date(2026, 11, 15))
    return {"first": first, "second": second, "deal": deal, "org": org}


def _weeks(world, workspace="first", weeks=6):
    with workspace_scope(world[workspace]):
        return get_weekly_hours(world[workspace], TODAY, weeks)


def test_there_are_weeks_from_this_monday_and_each_has_entered_and_expected_hours(world):
    result = _weeks(world, weeks=4)
    assert [w["start"] for w in result["weeks"]] == [date(2026, 11, 9), date(2026, 11, 16), date(2026, 11, 23), date(2026, 11, 30)]
    assert result["weeks"][0]["end"] == date(2026, 11, 15)
    assert all(w["entered"] == D("0") and w["expected"] == D("0") and w["total"] == D("0") for w in result["weeks"])
    assert result["capacity"] is None and result["has_expected"] is False


def test_hours_with_a_work_window_land_in_the_weeks_of_that_window(world):
    with workspace_scope(world["first"]):
        add_deal_sale(world["deal"], "2100", date(2026, 11, 1), "course", world["first"], status="booked", hours=D("21"),
                      work_from=date(2026, 11, 11), work_to=date(2026, 11, 24))          # Wed 11 to Tue 24 = 14 days
    entered = [w["entered"] for w in _weeks(world)["weeks"]]
    # 21 h over 14 days = 1.5 h a day: Wed-Sun 11-15 is 5 days, 16-22 is 7, Mon-Tue 23-24 is 2
    assert [round(float(h), 2) for h in entered[:4]] == [7.5, 10.5, 3.0, 0.0]


def test_hours_without_a_window_are_spread_over_the_month_they_are_due_in(world):
    with workspace_scope(world["first"]):
        add_deal_sale(world["deal"], "600", date(2026, 11, 1), "course", world["first"], status="booked", hours=D("30"),
                      expected_on=date(2026, 11, 20))                                   # November has 30 days: 1 h a day
    entered = [w["entered"] for w in _weeks(world, weeks=4)["weeks"]]
    assert [round(float(h), 2) for h in entered] == [7.0, 7.0, 7.0, 1.0]                  # 9-15, 16-22, 23-29, then 30 Nov only


def test_cancelled_sales_and_sales_without_hours_add_nothing_and_other_workspaces_are_invisible(world):
    with workspace_scope(world["first"]):
        add_deal_sale(world["deal"], "100", date(2026, 11, 1), "gone", world["first"], status="cancelled", hours=D("40"),
                      work_from=date(2026, 11, 9), work_to=date(2026, 11, 15))
        add_deal_sale(world["deal"], "100", date(2026, 11, 1), "no hours", world["first"], status="booked",
                      expected_on=date(2026, 11, 20))
    assert all(w["entered"] == D("0") for w in _weeks(world)["weeks"])
    assert _weeks(world, "second")["weeks"][0]["entered"] == D("500")


def test_a_persons_deal_counts_too(world):
    with workspace_scope(world["first"]):
        person = save_person("Pat Freelancer", source="test_fixture")
        with db() as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT offer_id_for(NULL, 'consulting') AS id")
            deal = add_deal("person", person, cursor.fetchone()["id"])
        add_deal_sale(deal, "100", date(2026, 11, 1), "coaching", world["first"], status="booked", hours=D("7"),
                      work_from=date(2026, 11, 9), work_to=date(2026, 11, 15))
    assert _weeks(world)["weeks"][0]["entered"] == D("7")


def test_the_expected_new_bookings_add_their_hours_a_week_in_blue_and_stop_with_the_campaign(world):
    with workspace_scope(world["first"]):
        save_expected_new_hours(D("3"), D("100"), None, 1, 2)                           # 3 h a week each, 2 months, from next month
    result = _weeks(world, weeks=8)
    expected = [w["expected"] for w in result["weeks"]]
    # weeks 9 and 16 Nov: November, nothing yet; 23 Nov: November; 30 Nov: December (1 booking, 3 h); January: 2 bookings (6 h)
    assert expected[:4] == [D("0"), D("0"), D("0"), D("3")] and result["has_expected"] is True
    assert all(w["total"] == w["entered"] + w["expected"] for w in result["weeks"])


def test_the_weekly_capacity_is_saved_and_returned(world):
    with workspace_scope(world["first"]):
        save_weekly_capacity(D("30"))
        assert get_plan()["weekly_capacity"] == D("30.00")
    assert _weeks(world)["capacity"] == D("30.00")
    with workspace_scope(world["first"]):
        for bad in (D("-1"), D("169"), "lots"):
            with pytest.raises(ValueError):
                save_weekly_capacity(bad)
        save_weekly_capacity(None)
        assert get_plan()["weekly_capacity"] is None
    with workspace_scope(world["second"]):
        assert get_plan()["weekly_capacity"] is None
