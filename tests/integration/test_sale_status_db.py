"""A sale's life on the real schema: booked → contracted → collected (or cancelled).
Only collected sales are money won; booked and contracted ones are the pipeline."""
from datetime import date
from decimal import Decimal

import pytest

from gcrm.db.connection import db
from gcrm.tools.db_organizations import save_organization
from gcrm.tools.db_people import save_person
from gcrm.tools.deal_money import add_deal_sale, deal_money, set_sale_status
from gcrm.tools.deal_records import DealNotFound, add_deal, get_deals
from gcrm.tools.statistics import add_sale, get_sales, get_statistics
from gcrm.tools.statistics_history import get_series

pytestmark = pytest.mark.integration

MONTH = (date(2026, 11, 1), date(2026, 11, 30))


@pytest.fixture
def firm(clean_database, monkeypatch):
    monkeypatch.setattr("gcrm.tools.db_organizations.geocode", lambda city, country: None)
    monkeypatch.setattr("gcrm.tools.db_people.geocode", lambda city, country: None)
    contact_id = save_organization("Brandt Maschinenbau", "Augsburg", pipeline_stage="prospect", source="test_fixture")
    deal_id = next(d["id"] for d in get_deals("organization", contact_id) if d["offer_slug"] == "consulting")
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug = 'default'")
        workspace = cursor.fetchone()["id"]
    return {"contact_id": contact_id, "deal": deal_id, "workspace": workspace}


def _stats(firm):
    return get_statistics(firm["workspace"], *MONTH, today=date(2026, 11, 30))


def _row(sale_id):
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT status, won_on, expected_on, collected_on FROM sales WHERE id = %s", (sale_id,))
        return cursor.fetchone()


def test_a_sale_is_collected_unless_said_otherwise_so_old_callers_keep_their_numbers(firm):
    sale = add_deal_sale(firm["deal"], "900", date(2026, 11, 3), "Workshop", firm["workspace"])
    row = _row(sale)
    assert row["status"] == "collected" and row["collected_on"] == date(2026, 11, 3)
    assert _stats(firm)["current"]["won_eur"] == Decimal("900")


def test_booked_money_is_pipeline_not_won(firm):
    add_deal_sale(firm["deal"], "2400", date(2026, 11, 3), "AI course", firm["workspace"],
                  status="booked", expected_on=date(2027, 1, 20))
    add_deal_sale(firm["deal"], "1000", date(2026, 11, 4), "Audit", firm["workspace"], status="contracted")
    stats = _stats(firm)
    assert stats["current"]["won_eur"] == Decimal("0") and stats["current"]["sales"] == 0
    assert stats["sales"] == []
    assert stats["pipeline"] == {"expected": {"eur": Decimal("0"), "count": 0},
                                 "booked": {"eur": Decimal("2400"), "count": 1},
                                 "contracted": {"eur": Decimal("1000"), "count": 1}}
    assert deal_money([firm["deal"]])[firm["deal"]]["sales_total"] == Decimal("0")
    assert deal_money([firm["deal"]])[firm["deal"]]["pipeline_total"] == Decimal("3400")


def test_moving_a_sale_along_to_collected_counts_it_on_the_day_the_money_came_in(firm):
    sale = add_deal_sale(firm["deal"], "2400", date(2026, 10, 20), "AI course", firm["workspace"], status="booked")
    assert set_sale_status(firm["deal"], sale, "contracted", workspace_id=firm["workspace"])
    assert _row(sale)["status"] == "contracted"
    assert set_sale_status(firm["deal"], sale, "collected", collected_on=date(2026, 11, 12),
                           workspace_id=firm["workspace"])
    row = _row(sale)
    assert (row["status"], row["won_on"], row["collected_on"]) == ("collected", date(2026, 10, 20), date(2026, 11, 12))
    assert _stats(firm)["current"]["won_eur"] == Decimal("2400")  # November, not October
    october = get_statistics(firm["workspace"], date(2026, 10, 1), date(2026, 10, 31), today=date(2026, 11, 30))
    assert october["current"]["won_eur"] == Decimal("0")
    series = get_series(firm["workspace"], "month", today=date(2026, 11, 30))
    assert series["periods"][-1]["won_eur"] == Decimal("2400")
    assert series["periods"][-2]["won_eur"] == Decimal("0")


def test_collecting_without_a_day_uses_today_and_leaving_collected_clears_it(firm):
    sale = add_deal_sale(firm["deal"], "500", date(2026, 11, 1), "", firm["workspace"], status="booked")
    set_sale_status(firm["deal"], sale, "collected", workspace_id=firm["workspace"])
    assert _row(sale)["collected_on"] == date.today()
    set_sale_status(firm["deal"], sale, "cancelled", workspace_id=firm["workspace"])
    row = _row(sale)
    assert (row["status"], row["collected_on"]) == ("cancelled", None)


def test_a_cancelled_sale_stays_listed_but_is_neither_won_nor_pipeline(firm):
    sale = add_deal_sale(firm["deal"], "700", date(2026, 11, 2), "Fell through", firm["workspace"], status="booked")
    set_sale_status(firm["deal"], sale, "cancelled", workspace_id=firm["workspace"])
    stats = _stats(firm)
    assert stats["pipeline"]["booked"] == {"eur": Decimal("0"), "count": 0}
    assert stats["current"]["won_eur"] == Decimal("0")
    (listed,) = get_sales(firm["contact_id"])
    assert listed["status"] == "cancelled" and listed["description"] == "Fell through"


def test_bad_input_is_refused(firm):
    with pytest.raises(ValueError):
        add_deal_sale(firm["deal"], "10", date(2026, 11, 2), "", firm["workspace"], status="paid")
    sale = add_deal_sale(firm["deal"], "10", date(2026, 11, 2), "", firm["workspace"], status="booked")
    with pytest.raises(ValueError):
        set_sale_status(firm["deal"], sale, "done", workspace_id=firm["workspace"])
    with pytest.raises(DealNotFound):
        set_sale_status(999999, sale, "collected", workspace_id=firm["workspace"])
    assert not set_sale_status(firm["deal"], 999999, "collected", workspace_id=firm["workspace"])
    other = save_organization("Other Firm", "Ulm", source="test_fixture")
    other_deal = next(d["id"] for d in get_deals("organization", other) if d["offer_slug"] == "consulting")
    assert not set_sale_status(other_deal, sale, "collected", workspace_id=firm["workspace"])  # not its deal
    assert _row(sale)["status"] == "booked"


def test_the_organization_form_path_takes_a_status_too(firm):
    sale = add_sale(firm["workspace"], firm["contact_id"], Decimal("1500"), date(2026, 11, 5), "Training",
                    status="booked", expected_on=date(2026, 12, 1))
    row = _row(sale)
    assert (row["status"], row["expected_on"]) == ("booked", date(2026, 12, 1))
    with pytest.raises(ValueError):
        add_sale(firm["workspace"], firm["contact_id"], Decimal("1"), date(2026, 11, 5), "", status="nope")


def test_a_person_who_is_a_consultant_can_have_sales_too(firm):
    consultant = save_person("Pat Freelancer", source="test_fixture")
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT offer_id_for(NULL, 'consulting') AS id")
        offer_id = cursor.fetchone()["id"]
    own = add_deal("person", consultant, offer_id)
    sale = add_deal_sale(own, "1200", date(2026, 11, 6), "Coaching", firm["workspace"], status="booked")
    assert deal_money([own])[own]["pipeline_total"] == Decimal("1200")
    set_sale_status(own, sale, "collected", collected_on=date(2026, 11, 20), workspace_id=firm["workspace"])
    stats = _stats(firm)
    assert stats["current"]["won_eur"] == Decimal("1200")
    assert stats["sales"][0]["organization"] == "Pat Freelancer"


def test_the_pages_show_status_pipeline_and_the_forms_to_move_a_sale(firm):
    from fastapi.testclient import TestClient

    import gcrm.api.main as main
    from gcrm.api.auth import require_admin, require_login

    add_deal_sale(firm["deal"], "2400", date(2026, 11, 3), "AI course", firm["workspace"],
                  status="booked", expected_on=date(2027, 1, 20))
    consultant = save_person("Pat Freelancer", source="test_fixture")
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT offer_id_for(NULL, 'consulting') AS id")
        own = add_deal("person", consultant, cursor.fetchone()["id"])
    add_deal_sale(own, "1200", date(2026, 11, 6), "Coaching", firm["workspace"], status="contracted")
    main.app.dependency_overrides[require_login] = lambda: "admin"
    main.app.dependency_overrides[require_admin] = lambda: "admin"
    try:
        web = TestClient(main.app)
        org_page = web.get(f"/organizations/{firm['contact_id']}?lang=en").text
        person_page = web.get(f"/people/{consultant}?lang=en").text
        stats_page = web.get("/statistics?start=2026-11-01&end=2026-11-30&lang=en").text
        recorded = web.post(f"/organizations/{firm['contact_id']}/sales", follow_redirects=False, data={
            "amount_eur": "800", "won_on": "2026-11-07", "status": "booked", "expected_on": "01.12.2026"})
        moved = web.post(f"/deals/{own}/sales/{get_sales_for_person(own)}/status", follow_redirects=False,
                         data={"status": "collected", "collected_on": "20.11.2026", "next": f"/people/{consultant}"})
    finally:
        main.app.dependency_overrides.pop(require_login, None)
        main.app.dependency_overrides.pop(require_admin, None)
    assert "badge-sale-booked" in org_page and "expected 20.01.2027" in org_page
    assert 'action="/deals/%d/sales/' % firm["deal"] in org_page
    assert "badge-sale-contracted" in person_page and f'action="/deals/{own}/sales"' in person_page
    assert "Booked, not collected yet" in person_page
    assert "Sales pipeline" in stats_page and "booked" in stats_page
    assert recorded.status_code == 303 and moved.status_code == 303
    assert _stats(firm)["current"]["won_eur"] == Decimal("1200")


def get_sales_for_person(deal_id: int) -> int:
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM sales WHERE deal_id = %s", (deal_id,))
        return cursor.fetchone()["id"]


def test_a_sale_can_start_as_an_expected_value_before_anything_is_booked(firm):
    from gcrm.sale_status import SALE_STATUSES
    assert SALE_STATUSES == ("expected", "booked", "contracted", "collected", "cancelled")
    sale = add_deal_sale(firm["deal"], "5000", date(2026, 11, 8), "Maybe a course", firm["workspace"], status="expected")
    assert _row(sale)["status"] == "expected" and _row(sale)["collected_on"] is None
    stats = _stats(firm)
    assert stats["pipeline"]["expected"] == {"eur": Decimal("5000"), "count": 1}
    assert stats["pipeline"]["booked"]["eur"] == Decimal("0")      # a hope is not firm pipeline
    assert stats["current"]["won_eur"] == Decimal("0")
    money = deal_money([firm["deal"]])[firm["deal"]]
    assert (money["expected_total"], money["pipeline_total"], money["sales_total"]) == (Decimal("5000"), Decimal("0"), Decimal("0"))


def test_an_expected_sale_moves_along_the_whole_way(firm):
    sale = add_deal_sale(firm["deal"], "800", date(2026, 11, 8), "", firm["workspace"], status="expected")
    for status in ("booked", "contracted", "collected"):
        assert set_sale_status(firm["deal"], sale, status, collected_on=date(2026, 11, 20), workspace_id=firm["workspace"])
        assert _row(sale)["status"] == status
    assert _stats(firm)["current"]["won_eur"] == Decimal("800")
    assert set_sale_status(firm["deal"], sale, "expected", workspace_id=firm["workspace"])   # a slip can be undone
    assert _row(sale)["collected_on"] is None
