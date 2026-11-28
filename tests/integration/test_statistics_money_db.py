"""The Statistics money figures, the per-contract sales table and the stuck list, on the real
schema. Data is shaped like live data: monthly contracts (one sale row per month, one contract),
nothing collected yet, no subscriptions, deals held by a person. All names are invented."""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from gcrm.db.connection import db
from gcrm.tools.db_deals import set_organization_deal
from gcrm.tools.db_people import save_person
from gcrm.tools.deal_money import add_deal_sale, start_subscription
from gcrm.tools.deal_records import add_deal
from gcrm.tools.statistics import get_statistics

pytestmark = pytest.mark.integration

TODAY = date(2026, 11, 28)
PERIOD = (date(2026, 11, 1), date(2026, 11, 30))


def _workspace() -> int:
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug = 'default'")
        return cursor.fetchone()["id"]


def _organization(name: str, stage: str = "prospect", created: str = "2026-06-01") -> tuple[int, int]:
    """An organization with one Consulting deal; returns (contact id, deal id)."""
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute(
            "INSERT INTO contacts (name, city, workspace_id, created_at) VALUES (%s, 'Augsburg', "
            "(SELECT id FROM workspaces WHERE slug = 'default'), %s) RETURNING id", (name, created))
        contact_id = cursor.fetchone()["id"]
        set_organization_deal(cursor, contact_id, stage=stage, status="none")
        cursor.execute("SELECT id FROM deals WHERE contact_id = %s", (contact_id,))
        return contact_id, cursor.fetchone()["id"]


def _age_deal(deal_id: int, created: str) -> None:
    """Make the deal old: created long ago, and its stage entered then too."""
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("UPDATE deals SET created_at = %s WHERE id = %s", (created, deal_id))
        cursor.execute("UPDATE stage_changes SET changed_at = %s WHERE deal_id = %s", (created, deal_id))


def _contract(deal: int, total: str, status: str, months: int, title: str, won_on=date(2026, 11, 10)) -> int:
    return add_deal_sale(deal, total, won_on, "", _workspace(), status=status,
                         expected_on=date(2026, 12, 1) if months > 1 else None, months=months, title=title)


@pytest.fixture
def live_shaped(clean_database):
    """Monthly contracts expected / booked / contracted, one single booked sale, one cancelled
    contract, nothing collected, no subscription."""
    workspace = _workspace()
    _, first = _organization("Harbour Bakery Ltd")
    _, second = _organization("Orchard Tools GmbH")
    _contract(first, "3000", "booked", 3, "Monthly coaching")            # 3 rows of 1000, one contract
    _contract(first, "1200", "expected", 3, "Monthly advice")            # 3 rows of 400
    _contract(second, "500", "contracted", 1, "One workshop")
    _contract(second, "700", "cancelled", 1, "Fell through")
    _contract(second, "900", "booked", 1, "Last month", won_on=date(2026, 10, 12))   # previous period
    return {"workspace": workspace, "first": first, "second": second}


def test_sold_and_expected_count_each_contract_once_not_each_monthly_payment(live_shaped):
    current = get_statistics(live_shaped["workspace"], *PERIOD, today=TODAY)["current"]

    assert (current["sold_eur"], current["sold_contracts"]) == (Decimal("3500"), 2)   # 3000 + 500
    assert (current["expected_eur"], current["expected_contracts"]) == (Decimal("1200"), 1)
    assert current["collected_eur"] == Decimal("0")
    for gone in ("won_eur", "eur_per_hour", "sales", "hours"):
        assert gone not in current


def test_the_previous_period_has_its_own_money_figures_for_the_deltas(live_shaped):
    previous = get_statistics(live_shaped["workspace"], *PERIOD, today=TODAY)["previous"]
    assert (previous["sold_eur"], previous["sold_contracts"]) == (Decimal("900"), 1)
    assert (previous["expected_eur"], previous["expected_contracts"]) == (Decimal("0"), 0)


def test_collected_money_is_counted_by_the_day_it_came_in_and_is_also_sold(clean_database):
    _, deal = _organization("Quarry Supplies AG")
    add_deal_sale(deal, "800", date(2026, 10, 20), "", _workspace(), status="collected",
                  collected_on=date(2026, 11, 5))
    november = get_statistics(_workspace(), *PERIOD, today=TODAY)["current"]
    assert (november["collected_eur"], november["sold_eur"]) == (Decimal("800"), Decimal("0"))  # agreed in October
    october = get_statistics(_workspace(), date(2026, 10, 1), date(2026, 10, 31), today=TODAY)["current"]
    assert (october["collected_eur"], october["sold_eur"], october["sold_contracts"]) == (
        Decimal("0"), Decimal("800"), 1)


def test_open_now_stays_all_time_firm_and_expected(live_shaped):
    pipeline = get_statistics(live_shaped["workspace"], *PERIOD, today=TODAY)["pipeline"]
    assert pipeline["booked"]["eur"] == Decimal("3900") and pipeline["contracted"]["eur"] == Decimal("500")
    assert pipeline["expected"]["eur"] == Decimal("1200")


def test_mrr_tiles_are_shown_only_when_a_subscription_exists_whatever_the_offer_filter(live_shaped):
    workspace = live_shaped["workspace"]
    assert get_statistics(workspace, *PERIOD, today=TODAY)["has_subscriptions"] is False
    contact, _ = _organization("Meadow School")
    learnwohl = add_deal("organization", contact, _offer_id("learnwohl"))
    start_subscription(learnwohl, "30", date(2026, 11, 1))
    assert get_statistics(workspace, *PERIOD, today=TODAY)["has_subscriptions"] is True
    assert get_statistics(workspace, *PERIOD, today=TODAY, offer="consulting")["has_subscriptions"] is True


def _offer_id(slug: str) -> int:
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT offer_id_for(NULL, %s) AS id", (slug,))
        return cursor.fetchone()["id"]


def test_the_sales_table_has_one_row_per_contract_with_the_total_of_its_payments(live_shaped):
    sales = get_statistics(live_shaped["workspace"], *PERIOD, today=TODAY)["sales"]

    by_title = {row["title"]: row for row in sales}
    assert sorted(by_title) == ["Monthly advice", "Monthly coaching", "One workshop"]   # cancelled one is left out
    coaching = by_title["Monthly coaching"]
    assert (coaching["amount_eur"], coaching["payments"], coaching["status"]) == (Decimal("3000.00"), 3, "booked")
    assert coaching["organization"] == "Harbour Bakery Ltd" and coaching["won_on"] == date(2026, 11, 10)
    assert by_title["Monthly advice"]["status"] == "expected" and by_title["One workshop"]["payments"] == 1


def test_weeks_and_activities_run_from_the_previous_contract_of_the_same_organization(live_shaped):
    contact, deal = _organization("Lantern Printers Ltd", created="2026-08-01")
    add_deal_sale(deal, "400", date(2026, 10, 6), "", _workspace(), status="booked", title="First job")
    add_deal_sale(deal, "600", date(2026, 11, 3), "", _workspace(), status="booked", title="Second job")
    with db() as connection:
        connection.cursor().execute(
            "INSERT INTO interactions (contact_id, interaction_date, method, outcome, summary) VALUES "
            "(%s, '2026-10-01', 'meeting', 'note', 'x'), (%s, '2026-10-20', 'phone', 'note', 'x'), "
            "(%s, '2026-10-28', 'email', 'note', 'x')", (contact, contact, contact))
    sales = get_statistics(live_shaped["workspace"], *PERIOD, today=TODAY)["sales"]
    second = next(row for row in sales if row["title"] == "Second job")
    assert second["weeks"] == 4.0                      # 6.10. to 3.11. = 28 days
    assert second["activities"] == 2                   # 20.10. and 28.10.; the 1.10. one belongs to the first job


def test_a_person_held_working_deal_with_no_recent_activity_is_stuck_and_links_to_the_person(clean_database, monkeypatch):
    monkeypatch.setattr("gcrm.tools.db_people.geocode", lambda city, country: None)
    solo = save_person("Mira Tester", source="test_fixture", allow_duplicate=True)
    deal = add_deal("person", solo, _offer_id("consulting"))
    with db() as connection:
        connection.cursor().execute("UPDATE deals SET pipeline_stage = 'nibble' WHERE id = %s", (deal,))
    _age_deal(deal, "2026-08-01")

    stats = get_statistics(_workspace(), *PERIOD, today=TODAY)

    (row,) = stats["stuck"]
    assert (row["name"], row["person_id"], row["id"], row["pipeline_stage"]) == ("Mira Tester", solo, None, "nibble")
    assert row["last_day"] is None and row["added_on"] == "2026-08-01"
    assert stats["stuck_total"] == 1


def test_a_recent_person_activity_keeps_a_person_deal_out_of_the_stuck_list(clean_database, monkeypatch):
    monkeypatch.setattr("gcrm.tools.db_people.geocode", lambda city, country: None)
    solo = save_person("Mira Tester", source="test_fixture", allow_duplicate=True)
    deal = add_deal("person", solo, _offer_id("consulting"))
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("UPDATE deals SET pipeline_stage = 'nibble' WHERE id = %s", (deal,))
        cursor.execute("INSERT INTO people_interactions (person_id, occurred_at, method, note) "
                       "VALUES (%s, %s, 'call', 'x')", (solo, TODAY - timedelta(days=3)))
    _age_deal(deal, "2026-08-01")
    assert get_statistics(_workspace(), *PERIOD, today=TODAY)["stuck"] == []


def test_a_brand_new_organization_is_not_stuck_but_an_old_silent_one_is(clean_database):
    _, fresh = _organization("Brand New Ltd", created=TODAY.isoformat())
    with db() as connection:
        connection.cursor().execute("UPDATE deals SET created_at = %s WHERE id = %s", (TODAY, fresh))
    old, old_deal = _organization("Old Silent Ltd")
    _age_deal(old_deal, "2026-06-01")
    stats = get_statistics(_workspace(), *PERIOD, today=TODAY)
    assert [row["name"] for row in stats["stuck"]] == ["Old Silent Ltd"]
    assert stats["stuck"][0]["id"] == old and stats["stuck"][0]["person_id"] is None


def test_an_inbound_message_counts_as_activity_but_a_next_step_entry_does_not(clean_database):
    heard, heard_deal = _organization("Heard From Ltd")
    planned, planned_deal = _organization("Only Planned Ltd")
    _age_deal(heard_deal, "2026-06-01")
    _age_deal(planned_deal, "2026-06-01")
    with db() as connection:
        connection.cursor().execute(
            "INSERT INTO interactions (contact_id, interaction_date, method, direction, outcome, summary) VALUES "
            "(%s, %s, 'email', 'inbound', 'note', 'they wrote'), (%s, %s, 'next_step', NULL, 'note', 'plan')",
            (heard, TODAY - timedelta(days=2), planned, TODAY - timedelta(days=2)))
    names = [row["name"] for row in get_statistics(_workspace(), *PERIOD, today=TODAY)["stuck"]]
    assert names == ["Only Planned Ltd"]


def test_entering_the_current_stage_recently_resets_the_clock(clean_database):
    _, deal = _organization("Moved Up Ltd")
    _age_deal(deal, "2026-06-01")
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("UPDATE deals SET pipeline_stage = 'nibble' WHERE id = %s", (deal,))   # the trigger logs it
        cursor.execute("UPDATE stage_changes SET changed_at = %s WHERE deal_id = %s",
                       (TODAY - timedelta(days=5), deal))
    assert get_statistics(_workspace(), *PERIOD, today=TODAY)["stuck"] == []


def test_the_stuck_list_shows_25_and_reports_the_total(clean_database):
    for number in range(27):
        _, deal = _organization(f"Silent Firm {number:02d}")
        _age_deal(deal, "2026-06-01")
    stats = get_statistics(_workspace(), *PERIOD, today=TODAY)
    assert len(stats["stuck"]) == 25 and stats["stuck_total"] == 27
