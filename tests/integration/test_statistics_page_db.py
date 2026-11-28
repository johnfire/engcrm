"""The Statistics page rendered from data shaped like the live workspace: monthly contracts in
several statuses, nothing collected, no subscription, a deal held by a person, a brand-new
organization. Names are invented."""
import re
from datetime import date

import pytest
from fastapi.testclient import TestClient

import gcrm.api.main as main
from gcrm.api.auth import require_admin, require_login
from gcrm.db.connection import db
from gcrm.tools.db_deals import set_organization_deal
from gcrm.tools.db_people import save_person
from gcrm.tools.deal_money import add_deal_sale
from gcrm.tools.deal_records import add_deal
from gcrm.tools.statistics_history import record_pipeline_snapshot

pytestmark = pytest.mark.integration


def _workspace() -> int:
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug = 'default'")
        return cursor.fetchone()["id"]


def _organization(name: str, created: str) -> tuple[int, int]:
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("INSERT INTO contacts (name, workspace_id, created_at) VALUES (%s, %s, %s) RETURNING id",
                       (name, _workspace(), created))
        contact_id = cursor.fetchone()["id"]
        set_organization_deal(cursor, contact_id, stage="prospect", status="none")
        cursor.execute("UPDATE deals SET created_at = %s WHERE contact_id = %s RETURNING id", (created, contact_id))
        return contact_id, cursor.fetchone()["id"]


@pytest.fixture
def page(clean_database, monkeypatch):
    monkeypatch.setattr("gcrm.tools.db_people.geocode", lambda city, country: None)
    today = date.today()
    _, harbour = _organization("Harbour Bakery Ltd", "2026-01-05")
    for total, status, title in (("3000", "booked", "Monthly coaching"), ("1200", "expected", "Monthly advice"),
                                 ("2400", "contracted", "Quarterly workshop series")):
        add_deal_sale(harbour, total, today, "", _workspace(), status=status,
                      expected_on=date(today.year + 1, 1, 1), months=3, title=title)
    _organization("Brand New Ltd", today.isoformat())
    _organization("Old Silent Ltd", "2026-01-05")
    mira = save_person("Mira Tester", source="test_fixture", allow_duplicate=True)
    person_deal = add_deal("person", mira, _consulting_offer())
    with db() as connection:
        connection.cursor().execute(
            "UPDATE deals SET pipeline_stage = 'nibble', created_at = '2026-01-05' WHERE id = %s", (person_deal,))
        connection.cursor().execute("UPDATE stage_changes SET changed_at = '2026-01-05' WHERE deal_id = %s", (person_deal,))
    record_pipeline_snapshot(today)
    main.app.dependency_overrides[require_login] = lambda: "admin"
    main.app.dependency_overrides[require_admin] = lambda: "admin"
    try:
        yield {"client": TestClient(main.app), "mira": mira}
    finally:
        main.app.dependency_overrides.pop(require_login, None)
        main.app.dependency_overrides.pop(require_admin, None)


def _consulting_offer() -> int:
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT offer_id_for(NULL, 'consulting') AS id")
        return cursor.fetchone()["id"]


def _without_effort_and_minutes(html: str) -> str:
    """The page minus the Effort table and the default-minutes form, which stay as they are."""
    html = re.sub(r"<section class=\"detail-section\">\s*<h2>(?:Effort|Aufwand)</h2>.*?</section>", "", html, flags=re.S)
    return re.sub(r"<section class=\"detail-section\">\s*<h2>(?:Default minutes per activity|Standardminuten pro Aktivität)</h2>.*?</section>", "", html, flags=re.S)


def _tile(html: str, label: str) -> str:
    match = re.search(rf'stat-tile__label"[^>]*>{label}</span>\s*<strong class="stat-tile__value">([^<]*)</strong>', html)
    assert match, f"no tile {label!r}"
    return match.group(1)


def test_sold_and_expected_are_non_zero_and_each_contract_is_counted_once(page):
    html = page["client"].get("/statistics?period=year&lang=en").text
    assert _tile(html, "Sold") == "5.400 €"                 # 3000 booked + 2400 contracted
    assert _tile(html, "Contracts sold") == "2"             # 6 monthly payments, 2 contracts
    assert _tile(html, "Expected") == "1.200 €"
    assert _tile(html, "Collected") == "0 €"
    assert "Open now (all time)" in html and "Moved forward" in html


def test_there_are_no_mrr_tiles_without_a_subscription(page):
    html = page["client"].get("/statistics?lang=en").text
    for label in ("Monthly recurring now", "Subscription revenue"):
        assert label not in html


def test_the_word_hours_appears_only_in_the_effort_table_and_the_minutes_form(page):
    for language, words in (("en", ("hours", "per hour")), ("de", ("stunden", "pro stunde"))):
        html = _without_effort_and_minutes(page["client"].get(f"/statistics?lang={language}").text)
        text = re.sub(r"<[^>]+>", " ", html).lower()
        for word in words:
            assert word not in text, word
        assert "stat-bars" not in html and "stat-multiple" not in html


def test_the_stacked_chart_is_there_and_the_sales_table_has_one_row_per_contract(page):
    html = page["client"].get("/statistics?period=year&lang=en&trend=week").text
    assert html.count('<svg class="chart chart--stacked"') == 1 and "chart-segment--nibble" in html
    assert "Candidates" in html and "Dropped (not in pipeline)" in html
    table = html.split("Sales and the work behind them")[1].split("</table>")[0]
    assert table.count("<tr>") == 1 + 3                     # header and three contracts
    assert "Monthly coaching" in table and "Quarterly workshop series" in table


def test_the_person_deal_is_in_the_stuck_list_and_the_brand_new_organization_is_not(page):
    html = page["client"].get("/statistics?lang=en").text
    stuck = html.split("Stuck: working stage")[1].split("</section>")[0]
    assert f'href="/people/{page["mira"]}">Mira Tester</a>' in stuck
    assert "Old Silent Ltd" in stuck and "Brand New Ltd" not in stuck
    assert "added on 05.01.2026, no activity yet" in stuck


def test_the_expected_tile_explains_the_status_in_english_and_german(page):
    english = page["client"].get("/statistics?lang=en").text
    german = page["client"].get("/statistics?lang=de").text
    assert "Estimated: a conservative forecast built on solid facts" in english
    assert "Geschätzt: eine vorsichtige Prognose auf der Grundlage solider Tatsachen" in german
    assert "Weitergekommen" in german and "Verkauft" in german and "Erwartet" in german
