"""The daily pipeline log and the over-time series, on the real schema."""
import threading
from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

import gcrm.api.main as main
from gcrm.api.auth import require_admin, require_login
from gcrm.db.connection import db
from gcrm.tools.db_deals import set_organization_deal
from gcrm.tools.statistics import add_sale
from gcrm.tools.statistics_history import get_series, record_pipeline_snapshot

pytestmark = pytest.mark.integration
TODAY = date(2026, 10, 15)


def _workspace() -> int:
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug = 'default'")
        return cursor.fetchone()["id"]


def _organization(name: str, stage: str, created: str = "2026-10-01") -> int:
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute(
            "INSERT INTO contacts (name, workspace_id, created_at) "
            "VALUES (%s, (SELECT id FROM workspaces WHERE slug = 'default'), %s) RETURNING id",
            (name, created),
        )
        contact_id = cursor.fetchone()["id"]
        set_organization_deal(cursor, contact_id, stage=stage, status="none")
        return contact_id


def _snapshot_rows(day: date) -> dict:
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT entity_type, stage, n FROM pipeline_snapshots WHERE day = %s", (day,))
        return {(r["entity_type"], r["stage"]): r["n"] for r in cursor.fetchall()}


def test_a_snapshot_counts_each_stage_and_a_later_one_replaces_the_day(clean_database):
    a = _organization("A", "prospect")
    _organization("B", "prospect")
    _organization("C", "candidate")

    record_pipeline_snapshot(TODAY)
    assert _snapshot_rows(TODAY) == {("organization", "prospect"): 2, ("organization", "candidate"): 1}

    with db() as connection:
        set_organization_deal(connection.cursor(), a, stage="customer")
    record_pipeline_snapshot(TODAY)
    assert _snapshot_rows(TODAY) == {("organization", "prospect"): 1, ("organization", "candidate"): 1,
                                     ("organization", "customer"): 1}


def test_each_offer_is_logged_separately_and_the_series_shows_consulting(clean_database):
    workspace = _workspace()
    acme = _organization("Acme", "prospect")
    with db() as connection:
        set_organization_deal(connection.cursor(), acme, stage="customer", offer="learnwohl")
    record_pipeline_snapshot(TODAY)

    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT o.slug, s.stage, s.n FROM pipeline_snapshots s JOIN offers o ON o.id = s.offer_id "
                       "WHERE s.day = %s ORDER BY o.slug", (TODAY,))
        assert [tuple(r.values()) for r in cursor.fetchall()] == [("consulting", "prospect", 1),
                                                                   ("learnwohl", "customer", 1)]
    assert get_series(workspace, "month", today=TODAY)["pipeline"]["organization"] == {
        "prospect": {date(2026, 10, 1): 1}}


def test_two_workers_snapshotting_at_once_do_not_collide(clean_database):
    _organization("A", "prospect")
    errors = []

    def run():
        try:
            record_pipeline_snapshot(TODAY)
        except Exception as error:  # pragma: no cover - the assertion reports it
            errors.append(error)

    threads = [threading.Thread(target=run) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == [] and _snapshot_rows(TODAY) == {("organization", "prospect"): 1}


def test_series_per_month_reach_back_and_the_pipeline_uses_each_months_last_logged_day(clean_database):
    workspace = _workspace()
    acme = _organization("Acme", "prospect", created="2026-08-10")
    with db() as connection:
        connection.cursor().execute(
            "INSERT INTO interactions (contact_id, interaction_date, method, outcome, summary) "
            "VALUES (%s, '2026-08-12', 'meeting', 'note', 'x'), (%s, '2026-10-02', 'phone', 'note', 'x')",
            (acme, acme),
        )
    add_sale(workspace, acme, Decimal("1200"), date(2026, 9, 20), "Painting")
    record_pipeline_snapshot(date(2026, 9, 3))
    with db() as connection:
        set_organization_deal(connection.cursor(), acme, stage="customer")
    record_pipeline_snapshot(date(2026, 9, 28))

    series = get_series(workspace, "month", today=TODAY)

    by_month = {p["start"]: p for p in series["periods"]}
    assert by_month[date(2026, 8, 1)]["hours"] == 0.8 and by_month[date(2026, 8, 1)]["activities"] == 1
    assert by_month[date(2026, 9, 1)]["won_eur"] == Decimal("1200")
    assert by_month[date(2026, 10, 1)]["hours"] == 0.2  # a 15-minute call
    assert by_month[date(2026, 8, 1)]["new_organizations"] == 1
    org = series["pipeline"]["organization"]
    assert org.get("customer") == {date(2026, 9, 1): 1}   # the 28th, not the 3rd
    assert "prospect" not in org
    assert series["logged_since"] == date(2026, 9, 3)


def test_the_page_draws_the_charts(clean_database):
    _organization("Acme", "prospect")
    record_pipeline_snapshot(date.today() - timedelta(days=1))
    record_pipeline_snapshot(date.today())
    main.app.dependency_overrides[require_login] = lambda: "admin"
    main.app.dependency_overrides[require_admin] = lambda: "admin"
    try:
        page = TestClient(main.app).get("/statistics?trend=week&lang=en")
    finally:
        main.app.dependency_overrides.pop(require_login, None)
        main.app.dependency_overrides.pop(require_admin, None)
    assert page.status_code == 200, page.text[:500]
    assert page.text.count('<svg class="chart"') == 5
    assert 'aria-label="Organization · Prospect"' in page.text
    assert 'aria-current="true">Weekly</a>' in page.text
