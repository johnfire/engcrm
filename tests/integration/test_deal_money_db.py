"""Money per offer on the real schema: subscriptions and price changes, the
calculated subscription revenue, MRR, sales on deals, statistics by offer, and a
paying customer kept by retention."""
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

import gcrm.api.main as main
from gcrm.api.auth import require_admin, require_login
from gcrm.db.connection import db
from gcrm.tools.db_deals import set_organization_deal
from gcrm.tools.db_organizations import save_organization
from gcrm.tools.db_people import save_person
from gcrm.tools.deal_money import add_deal_sale, deal_money, end_subscription, start_subscription
from gcrm.tools.deal_records import add_deal, get_deals
from gcrm.tools.privacy_retention import purge_expired_data
from gcrm.tools.statistics import add_sale, get_statistics

pytestmark = pytest.mark.integration


@pytest.fixture
def school(clean_database, monkeypatch):
    """A language school: a Consulting deal, and a LearnWohl deal."""
    monkeypatch.setattr("gcrm.tools.db_organizations.geocode", lambda city, country: None)
    monkeypatch.setattr("gcrm.tools.db_people.geocode", lambda city, country: None)
    contact_id = save_organization("Simmons Language School", "Hannover", pipeline_stage="prospect",
                                   source="test_fixture")
    with db() as connection:
        set_organization_deal(connection.cursor(), contact_id, stage="customer", offer="learnwohl")
    deals = {d["offer_slug"]: d["id"] for d in get_deals("organization", contact_id)}
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug = 'default'")
        workspace = cursor.fetchone()["id"]
    return {"contact_id": contact_id, "workspace": workspace, **deals}


def _subscriptions(deal_id: int) -> list[tuple]:
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT amount_eur_month, started_on, ended_on FROM subscriptions "
                       "WHERE deal_id = %s AND deleted_at IS NULL ORDER BY started_on", (deal_id,))
        return [tuple(r.values()) for r in cursor.fetchall()]


def test_a_price_change_ends_the_old_price_the_day_before(school):
    start_subscription(school["learnwohl"], "49", date(2026, 9, 1))
    start_subscription(school["learnwohl"], "59", date(2026, 11, 1))
    assert _subscriptions(school["learnwohl"]) == [
        (Decimal("49.00"), date(2026, 9, 1), date(2026, 10, 31)),
        (Decimal("59.00"), date(2026, 11, 1), None)]
    with pytest.raises(ValueError):  # would overlap the price that starts on Nov 1
        start_subscription(school["learnwohl"], "39", date(2026, 11, 1))
    with pytest.raises(ValueError):
        end_subscription(school["learnwohl"], date(2026, 10, 1))  # before the running one started
    assert end_subscription(school["learnwohl"], date(2026, 12, 31))
    assert not end_subscription(school["learnwohl"], date(2027, 1, 31))  # nothing running


def test_subscription_revenue_is_per_day_and_the_mrr_counts_new_not_repriced(school):
    # €30/month from Sep 16: Sep is 15 of 30 days (15.00), Oct 1-15 is 15 of 31 days (14.52)
    start_subscription(school["learnwohl"], "30", date(2026, 9, 16))
    start_subscription(school["learnwohl"], "60", date(2026, 10, 16))  # a price change, not new MRR
    stats = get_statistics(school["workspace"], date(2026, 9, 1), date(2026, 10, 15),
                           today=date(2026, 12, 1), offer="learnwohl")
    assert stats["current"]["subscription_eur"] == Decimal("29.52")
    assert (stats["current"]["new_mrr"], stats["current"]["lost_mrr"]) == (Decimal("30"), Decimal("0"))
    assert (stats["mrr_now"], stats["subscribers_now"]) == (Decimal("60"), 1)
    # revenue is calculated up to today, not for days still to come
    today = get_statistics(school["workspace"], date(2026, 10, 1), date(2026, 10, 31),
                           today=date(2026, 10, 16), offer="learnwohl")
    assert today["current"]["subscription_eur"] == Decimal("16.45")  # 15 days at 30 + 1 at 60, /31


def test_statistics_split_one_off_sales_and_subscriptions_by_offer(school):
    add_sale(school["workspace"], school["contact_id"], Decimal("2400"), date(2026, 10, 5), "Workshop")
    start_subscription(school["learnwohl"], "31", date(2026, 10, 1))
    args = (school["workspace"], date(2026, 10, 1), date(2026, 10, 10))
    consulting = get_statistics(*args, today=date(2026, 10, 10), offer="consulting")["current"]
    learnwohl = get_statistics(*args, today=date(2026, 10, 10), offer="learnwohl")["current"]
    everything = get_statistics(*args, today=date(2026, 10, 10))["current"]
    assert (consulting["one_off_eur"], consulting["subscription_eur"]) == (Decimal("2400"), Decimal("0"))
    assert (learnwohl["one_off_eur"], learnwohl["subscription_eur"]) == (Decimal("0"), Decimal("10.00"))
    assert everything["won_eur"] == Decimal("2410.00")


def test_sales_belong_to_an_organizations_deal(school):
    sale = add_sale(school["workspace"], school["contact_id"], Decimal("500"), date(2026, 10, 5), "Setup",
                    deal_id=school["learnwohl"])
    assert sale is not None
    assert deal_money([school["learnwohl"]])[school["learnwohl"]]["sales_total"] == Decimal("500")
    loner = save_person("Solo Teacher", source="test_fixture")
    own = add_deal("person", loner, school_offer_id("learnwohl"))
    with pytest.raises(ValueError):
        add_deal_sale(own, "100", date(2026, 10, 5))  # a person buys by subscription
    start_subscription(own, "19", date(2026, 10, 1))
    assert deal_money([own], today=date(2026, 10, 10))[own]["running"]["amount_eur_month"] == Decimal("19.00")


def school_offer_id(slug: str) -> int:
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT offer_id_for(NULL, %s) AS id", (slug,))
        return cursor.fetchone()["id"]


def test_a_paying_customer_is_kept_by_retention(school):
    lapsed = save_organization("Lapsed Gallery", "Ulm", source="test_fixture")
    with db() as connection:
        connection.cursor().execute("UPDATE contacts SET created_at = NOW() - INTERVAL '10 years'")
    start_subscription(school["learnwohl"], "49", date(2020, 1, 1))
    purge_expired_data()
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM contacts ORDER BY id")
        assert [r["id"] for r in cursor.fetchall()] == [school["contact_id"]]
    assert lapsed != school["contact_id"]


def test_the_card_and_the_statistics_page_show_the_money(school):
    start_subscription(school["learnwohl"], "49", date(2026, 9, 1))
    main.app.dependency_overrides[require_login] = lambda: "admin"
    main.app.dependency_overrides[require_admin] = lambda: "admin"
    try:
        client = TestClient(main.app)
        page = client.get(f"/organizations/{school['contact_id']}?lang=en").text
        stats = client.get("/statistics?offer=learnwohl&lang=en").text
        response = client.post(f"/deals/{school['learnwohl']}/subscription/end",
                               data={"ended_on": "2026-12-31"}, follow_redirects=False)
    finally:
        main.app.dependency_overrides.pop(require_login, None)
        main.app.dependency_overrides.pop(require_admin, None)
    assert "<strong>49 € / month</strong>" in page and "since 2026-09-01" in page
    assert "Monthly recurring now" in stats and "1 paying" in stats
    assert response.status_code == 303
