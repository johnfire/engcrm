"""Migration 111 on real Postgres: the backfill gives every existing sale a contract, the same way
the migration did, and running it again changes nothing.

The backfill is the SQL function `backfill_sale_contracts()`. Each test works inside one transaction
that is rolled back (Postgres DDL is transactional): it lets `sales.contract_id` be empty again, seeds
sales the way production held them before the migration, and calls the function."""
from datetime import date
from pathlib import Path

import psycopg2
import psycopg2.extras
import pytest

from gcrm.db.connection import db
from gcrm.tools.db_organizations import save_organization
from gcrm.tools.deal_records import get_deals

pytestmark = pytest.mark.integration

MIGRATION = Path(__file__).parents[2] / "gcrm" / "db" / "migrations" / "111_contracts.sql"
SERIES = "11111111-1111-1111-1111-111111111111"
PARTLY_DELETED = "22222222-2222-2222-2222-222222222222"
ALL_DELETED = "33333333-3333-3333-3333-333333333333"


@pytest.fixture
def deal(clean_database, monkeypatch):
    monkeypatch.setattr("gcrm.tools.db_organizations.geocode", lambda city, country: None)
    school = save_organization("VHS Musterstadt", "Augsburg", source="test_fixture")
    return next(d["id"] for d in get_deals("organization", school) if d["offer_slug"] == "consulting")


@pytest.fixture
def raw(migrated_database, deal):
    """A transaction on the operator connection, rolled back at the end, in which the NOT NULL is lifted.
    It needs `deal` so the data is made first: the ALTER below holds a lock on `sales` until the rollback,
    and the database cleaning that `deal` does would wait on it for ever."""
    connection = psycopg2.connect(migrated_database, cursor_factory=psycopg2.extras.RealDictCursor)
    cursor = connection.cursor()
    cursor.execute("ALTER TABLE sales ALTER COLUMN contract_id DROP NOT NULL")
    yield cursor
    connection.rollback()
    connection.close()


def _sale(cursor, deal, description, won_on=date(2026, 11, 5), series=None, part=None, total=None, deleted=False,
          status="booked"):
    cursor.execute(
        "INSERT INTO sales (workspace_id, deal_id, amount_eur, won_on, description, status, expected_on, series_id, "
        "series_part, series_total, deleted_at, created_at) "
        "SELECT workspace_id, id, 100, %s, %s, %s, %s, %s::uuid, %s, %s, CASE WHEN %s THEN NOW() END, "
        "%s::timestamptz + make_interval(secs => %s) FROM deals WHERE id = %s RETURNING id",
        (won_on, description, status, date(2027, 1, 1), series, part, total, deleted, "2026-11-06 10:00", part or 0, deal))
    return cursor.fetchone()["id"]


def _seed(cursor, deal):
    ids = {}
    ids["series"] = [_sale(cursor, deal, "Year course", series=SERIES, part=n, total=3) for n in (1, 2, 3)]
    ids["single"] = _sale(cursor, deal, "One-day workshop")
    ids["blank"] = _sale(cursor, deal, "   ", won_on=date(2026, 3, 9))
    ids["null_description"] = _sale(cursor, deal, None, won_on=date(2026, 4, 2))
    ids["deleted"] = _sale(cursor, deal, "Mistyped", deleted=True)
    ids["partly"] = [_sale(cursor, deal, "Half gone", series=PARTLY_DELETED, part=1, total=2, deleted=True),
                     _sale(cursor, deal, "Half gone", series=PARTLY_DELETED, part=2, total=2)]
    ids["all_gone"] = [_sale(cursor, deal, "All gone", series=ALL_DELETED, part=n, total=2, deleted=True) for n in (1, 2)]
    return ids


def _contract_of(cursor, sale_id):
    cursor.execute("SELECT c.* FROM contracts c JOIN sales s ON s.contract_id = c.id WHERE s.id = %s", (sale_id,))
    return cursor.fetchone()


def _offer_name(cursor):
    cursor.execute("SELECT name FROM offers WHERE slug = 'consulting' LIMIT 1")
    return cursor.fetchone()["name"]


def test_one_contract_per_series_and_one_per_single_sale(raw, deal):
    ids = _seed(raw, deal)
    raw.execute("SELECT backfill_sale_contracts() AS made")
    assert raw.fetchone()["made"] == 7           # series, single, blank, null description, deleted, partly, all gone
    raw.execute("SELECT count(*) AS n FROM contracts WHERE deal_id = %s", (deal,))
    assert raw.fetchone()["n"] == 7
    series_contracts = {_contract_of(raw, sale)["id"] for sale in ids["series"]}
    assert len(series_contracts) == 1
    singles = {_contract_of(raw, ids[key])["id"] for key in ("single", "blank", "null_description", "deleted")}
    assert len(singles) == 4 and not singles & series_contracts


def test_no_sale_is_left_without_a_contract_and_each_contract_is_on_its_sales_deal_and_workspace(raw, deal):
    _seed(raw, deal)
    raw.execute("SELECT backfill_sale_contracts()")
    raw.execute("SELECT count(*) AS n FROM sales WHERE contract_id IS NULL")
    assert raw.fetchone()["n"] == 0
    raw.execute("SELECT count(*) AS n FROM sales s JOIN contracts c ON c.id = s.contract_id "
                "WHERE c.deal_id <> s.deal_id OR c.workspace_id <> s.workspace_id")
    assert raw.fetchone()["n"] == 0


def test_titles_come_from_the_description_or_the_offer_and_month(raw, deal):
    ids = _seed(raw, deal)
    raw.execute("SELECT backfill_sale_contracts()")
    offer = _offer_name(raw)
    assert _contract_of(raw, ids["series"][0])["title"] == "Year course"
    assert _contract_of(raw, ids["single"])["title"] == "One-day workshop"
    assert _contract_of(raw, ids["blank"])["title"] == f"{offer} – 03.2026"
    assert _contract_of(raw, ids["null_description"])["title"] == f"{offer} – 04.2026"


def test_every_migrated_contract_is_of_kind_other_and_empty_of_assignment(raw, deal):
    _seed(raw, deal)
    raw.execute("SELECT backfill_sale_contracts()")
    raw.execute("SELECT DISTINCT kind, assignment, contact_person_id FROM contracts WHERE deal_id = %s", (deal,))
    assert [dict(row) for row in raw.fetchall()] == [{"kind": "other", "assignment": "", "contact_person_id": None}]


def test_a_deleted_sale_gets_a_deleted_contract_and_a_series_only_when_every_payment_is_deleted(raw, deal):
    ids = _seed(raw, deal)
    raw.execute("SELECT backfill_sale_contracts()")
    assert _contract_of(raw, ids["deleted"])["deleted_at"] is not None
    assert _contract_of(raw, ids["all_gone"][0])["deleted_at"] is not None
    assert _contract_of(raw, ids["partly"][0])["deleted_at"] is None            # one payment is still alive
    assert _contract_of(raw, ids["single"])["deleted_at"] is None
    assert _contract_of(raw, ids["series"][0])["deleted_at"] is None


def test_a_contract_is_created_when_its_first_payment_was(raw, deal):
    ids = _seed(raw, deal)
    raw.execute("SELECT backfill_sale_contracts()")
    raw.execute("SELECT created_at FROM sales WHERE id = %s", (ids["series"][0],))
    first_payment = raw.fetchone()["created_at"]
    assert _contract_of(raw, ids["series"][2])["created_at"] == first_payment


def test_the_sales_themselves_are_not_touched(raw, deal):
    ids = _seed(raw, deal)
    columns = "id, amount_eur, won_on, description, status, expected_on, series_id, series_part, series_total, deleted_at"
    raw.execute(f"SELECT {columns} FROM sales ORDER BY id")
    before = [dict(row) for row in raw.fetchall()]
    raw.execute("SELECT backfill_sale_contracts()")
    raw.execute(f"SELECT {columns} FROM sales ORDER BY id")
    assert [dict(row) for row in raw.fetchall()] == before and ids


def test_running_the_backfill_again_changes_nothing(raw, deal):
    _seed(raw, deal)
    raw.execute("SELECT backfill_sale_contracts()")
    raw.execute("SELECT * FROM contracts ORDER BY id")
    contracts = [dict(row) for row in raw.fetchall()]
    raw.execute("SELECT id, contract_id FROM sales ORDER BY id")
    sales = [dict(row) for row in raw.fetchall()]
    raw.execute("SELECT backfill_sale_contracts() AS made")
    assert raw.fetchone()["made"] == 0
    raw.execute("SELECT * FROM contracts ORDER BY id")
    assert [dict(row) for row in raw.fetchall()] == contracts
    raw.execute("SELECT id, contract_id FROM sales ORDER BY id")
    assert [dict(row) for row in raw.fetchall()] == sales


def test_a_sale_added_later_is_picked_up_without_disturbing_the_rest(raw, deal):
    ids = _seed(raw, deal)
    raw.execute("SELECT backfill_sale_contracts()")
    raw.execute("SELECT count(*) AS n FROM contracts")
    contracts_before = raw.fetchone()["n"]
    late = _sale(raw, deal, "Late arrival")
    raw.execute("SELECT backfill_sale_contracts() AS made")
    assert raw.fetchone()["made"] == 1
    raw.execute("SELECT count(*) AS n FROM contracts")
    assert raw.fetchone()["n"] == contracts_before + 1
    assert _contract_of(raw, late)["title"] == "Late arrival"
    assert _contract_of(raw, ids["series"][0])["title"] == "Year course"


def test_running_the_whole_migration_file_again_changes_nothing(raw, deal):
    _seed(raw, deal)
    raw.execute("SELECT backfill_sale_contracts()")
    raw.execute("SELECT count(*) AS n FROM contracts")
    before = raw.fetchone()["n"]
    raw.execute(MIGRATION.read_text())
    raw.execute("SELECT count(*) AS n FROM contracts")
    assert raw.fetchone()["n"] == before
    raw.execute("SELECT is_nullable FROM information_schema.columns WHERE table_name = 'sales' AND column_name = 'contract_id'")
    assert raw.fetchone()["is_nullable"] == "NO"


# --- the schema the migration leaves behind --------------------------------

def test_the_migration_leaves_contract_id_required_and_tied_to_the_same_deal(migrated_database):
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT is_nullable FROM information_schema.columns "
                       "WHERE table_name = 'sales' AND column_name = 'contract_id'")
        assert cursor.fetchone()["is_nullable"] == "NO"
        cursor.execute("SELECT pg_get_constraintdef(oid) AS definition FROM pg_constraint "
                       "WHERE conrelid = 'sales'::regclass AND contype = 'f' AND confrelid = 'contracts'::regclass")
        (foreign_key,) = [row["definition"] for row in cursor.fetchall()]
        assert "(contract_id, deal_id)" in foreign_key and "contracts(id, deal_id)" in foreign_key
        assert "ON DELETE CASCADE" in foreign_key
        cursor.execute("SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class "
                       "WHERE relname IN ('contracts', 'contract_links') ORDER BY relname")
        assert [dict(row) for row in cursor.fetchall()] == [
            {"relname": "contract_links", "relrowsecurity": True, "relforcerowsecurity": True},
            {"relname": "contracts", "relrowsecurity": True, "relforcerowsecurity": True}]
