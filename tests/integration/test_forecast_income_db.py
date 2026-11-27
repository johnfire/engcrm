"""The calculator's Forecast query on the real schema."""
from datetime import date
from decimal import Decimal

import pytest

from gcrm.db.connection import db
from gcrm.tools.db_organizations import save_organization
from gcrm.tools.deal_money import add_deal_sale, set_sale_status
from gcrm.tools.deal_records import get_deals
from gcrm.tools.forecast_income import get_forecast_income
from gcrm.tools.income_plan import save_expected_new_sales
from gcrm.workspace_context import workspace_scope

pytestmark = pytest.mark.integration
D = Decimal
TODAY = date(2026, 10, 15)
WON = date(2026, 9, 1)


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
    with workspace_scope(first):
        school = save_organization("VHS Musterstadt", "Augsburg", source="test_fixture")
        deal = next(d["id"] for d in get_deals("organization", school) if d["offer_slug"] == "consulting")

        def sale(amount, title, kind, status, **when):
            return add_deal_sale(deal, amount, WON, title, first, status=status, title=title, kind=kind, **when)

        sale("1000", "Course", "teaching_course", "booked", expected_on=date(2026, 11, 1))
        sale("2000", "Contracted course", "teaching_course", "contracted", expected_on=date(2026, 12, 31))
        sale("300", "Advice", "consulting", "collected", collected_on=date(2026, 10, 1))
        sale("40", "Maybe", "teaching_course", "expected", expected_on=date(2026, 12, 1))
        sale("500", "Unlabelled", "other", "booked", expected_on=date(2026, 11, 1))
        sale("600", "No date", "teaching_course", "booked")
        sale("7000", "Next year", "teaching_course", "booked", expected_on=date(2027, 1, 1))
        lost = sale("8000", "Fell through", "teaching_course", "booked", expected_on=date(2026, 11, 1))
        set_sale_status(deal, lost, "cancelled", workspace_id=first)
        save_expected_new_sales("100", months=1, delay=0)
    return first, second


def lookup(workspace, **options):
    choices = {"include_expected": False, "include_possible": False, "possible_as": "consulting", **options}
    with workspace_scope(workspace):
        return get_forecast_income(workspace, 2026, today=TODAY, **choices)


def test_counts_this_years_live_money_by_contract_kind(world):
    income = lookup(world[0])
    assert (income.teaching, income.consulting) == (D("3000"), D("300"))
    assert [line.title for line in income.unclassified] == ["Unlabelled"]
    assert (income.undated_total, income.undated_count) == (D("600"), 1)
    assert income.possible == D("0")
    assert {line.customer for line in income.lines} == {"VHS Musterstadt"}


def test_expected_sales_and_possible_new_sales_are_opt_in(world):
    income = lookup(world[0], include_expected=True, include_possible=True)
    assert income.teaching == D("3040")
    # one-off bookings of 100 from November 2026 (the month after today), paid the same month
    assert income.possible == D("200")
    assert income.consulting == D("500")


def test_another_workspace_sees_none_of_it(world):
    income = lookup(world[1], include_expected=True, include_possible=True)
    assert (income.teaching, income.consulting, income.possible, income.lines) == (0, 0, 0, ())
