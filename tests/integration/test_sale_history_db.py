"""Every status a sale has had is written down with the time, so a later graph can show the
pipeline as it stood on any past day. Written by a trigger, so no screen, script or agent can forget it."""
from datetime import date
from pathlib import Path

import pytest

from gcrm.db.connection import db
from gcrm.tools.db_organizations import save_organization
from gcrm.tools.deal_money import add_deal_sale, set_sale_status, set_series_status
from gcrm.tools.deal_records import get_deals
from gcrm.tools.privacy_retention import erase_organization
from gcrm.workspace_context import workspace_scope

pytestmark = pytest.mark.integration


@pytest.fixture
def firm(clean_database, monkeypatch):
    monkeypatch.setattr("gcrm.tools.db_organizations.geocode", lambda city, country: None)
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug = 'default'")
        workspace = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO workspaces (slug, name) VALUES ('other-customer', 'Other') "
                       "ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name RETURNING id")
        other = cursor.fetchone()["id"]
    contact = save_organization("VHS Musterstadt", "Augsburg", pipeline_stage="prospect", source="test_fixture")
    deal = next(d["id"] for d in get_deals("organization", contact) if d["offer_slug"] == "consulting")
    return {"workspace": workspace, "other": other, "contact": contact, "deal": deal}


def _history(sale_id=None):
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT sale_id, from_status, to_status, workspace_id FROM sale_status_changes "
                       + ("WHERE sale_id = %s " if sale_id else "") + "ORDER BY id", (sale_id,) if sale_id else ())
        return [(r["from_status"], r["to_status"]) if sale_id else (r["sale_id"], r["from_status"], r["to_status"])
                for r in cursor.fetchall()]


def test_a_new_sale_is_recorded_with_the_status_it_started_as(firm):
    sale = add_deal_sale(firm["deal"], "500", date(2026, 11, 8), "", firm["workspace"], status="expected", expected_on=date(2027, 1, 1))
    assert _history(sale) == [(None, "expected")]


def test_every_move_is_recorded_in_order_and_a_save_without_a_change_is_not(firm):
    sale = add_deal_sale(firm["deal"], "500", date(2026, 11, 8), "", firm["workspace"], status="expected")
    for status in ("booked", "booked", "contracted", "collected", "cancelled", "expected"):
        set_sale_status(firm["deal"], sale, status, collected_on=date(2026, 12, 1), workspace_id=firm["workspace"])
    assert _history(sale) == [(None, "expected"), ("expected", "booked"), ("booked", "contracted"),
                              ("contracted", "collected"), ("collected", "cancelled"), ("cancelled", "expected")]


def test_a_whole_contract_move_records_each_payment_that_changed_and_not_the_received_one(firm):
    first = add_deal_sale(firm["deal"], "900", date(2026, 11, 8), "", firm["workspace"], status="booked",
                          expected_on=date(2027, 2, 1), months=3)
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id, series_id::text AS series FROM sales WHERE deal_id = %s ORDER BY series_part", (firm["deal"],))
        rows = cursor.fetchall()
    set_sale_status(firm["deal"], rows[0]["id"], "collected", collected_on=date(2027, 2, 3), workspace_id=firm["workspace"])
    assert set_series_status(firm["deal"], rows[0]["series"], "cancelled", workspace_id=firm["workspace"]) == 2
    assert _history(rows[0]["id"]) == [(None, "booked"), ("booked", "collected")]
    assert [_history(r["id"])[-1] for r in rows[1:]] == [("booked", "cancelled")] * 2
    assert first == rows[0]["id"]


def test_the_history_is_workspace_private(firm):
    sale = add_deal_sale(firm["deal"], "500", date(2026, 11, 8), "", firm["workspace"], status="booked")
    with workspace_scope(firm["workspace"]), db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT COUNT(*) AS n FROM sale_status_changes WHERE sale_id = %s", (sale,))
        assert cursor.fetchone()["n"] == 1
    with workspace_scope(firm["other"]), db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT COUNT(*) AS n FROM sale_status_changes")
        assert cursor.fetchone()["n"] == 0


def test_erasing_an_organization_removes_its_sales_history_too(firm):
    sale = add_deal_sale(firm["deal"], "500", date(2026, 11, 8), "", firm["workspace"], status="booked")
    assert _history(sale)
    assert erase_organization(firm["contact"])
    assert _history(sale) == []


def test_the_migration_gives_every_existing_sale_a_starting_row_dated_when_it_was_entered(firm):
    old = add_deal_sale(firm["deal"], "500", date(2026, 11, 8), "", firm["workspace"], status="collected")
    newer = add_deal_sale(firm["deal"], "700", date(2026, 11, 9), "", firm["workspace"], status="booked")
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("UPDATE sales SET created_at = TIMESTAMPTZ '2026-11-08 10:00+00' WHERE id = %s", (old,))
        cursor.execute("DROP TRIGGER IF EXISTS sales_status_history_insert ON sales")
        cursor.execute("DROP TRIGGER IF EXISTS sales_status_history_update ON sales")
        cursor.execute("DROP TABLE sale_status_changes")
        cursor.execute((Path("gcrm/db/migrations/089_sale_status_history.sql")).read_text())      # as if run on a database that has sales
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT sale_id, from_status, to_status, changed_at FROM sale_status_changes ORDER BY sale_id")
        rows = cursor.fetchall()
    assert [(r["sale_id"], r["from_status"], r["to_status"]) for r in rows] == [(old, None, "collected"), (newer, None, "booked")]
    assert rows[0]["changed_at"].isoformat().startswith("2026-11-08T10:00")
    set_sale_status(firm["deal"], newer, "contracted", workspace_id=firm["workspace"])        # and the trigger is back
    assert _history(newer) == [(None, "booked"), ("booked", "contracted")]
