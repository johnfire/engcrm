"""Contracts on the real schema: every sale belongs to one, the insert path makes it, and the
database itself refuses a payment on another deal's contract or a contract across workspaces."""
from datetime import date
from decimal import Decimal

import psycopg2
import pytest

from gcrm.db.connection import db
from gcrm.tools.db_organizations import save_organization
from gcrm.tools.db_people import save_person
from gcrm.tools.deal_money import add_deal_sale, create_contract, insert_sale_payments
from gcrm.tools.deal_records import get_deals
from gcrm.tools.statistics import add_sale
from gcrm.workspace_context import workspace_scope

pytestmark = pytest.mark.integration


def _deal(owner_id):
    return next(d["id"] for d in get_deals("organization", owner_id) if d["offer_slug"] == "consulting")


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
        other_school = save_organization("Berufsschule Beispiel", "Ulm", source="test_fixture")
        coordinator = save_person("Mara Beispiel", source="test_fixture", contact_id=school)
    with workspace_scope(second):
        foreign_org = save_organization("Kessler Logistik", "Ulm", source="test_fixture")
        foreign_person = save_person("Jonas Kessler", source="test_fixture", contact_id=foreign_org)
    return {"first": first, "second": second, "deal": _deal(school), "other_deal": _deal(other_school),
            "foreign_deal": _deal(foreign_org), "coordinator": coordinator, "foreign_person": foreign_person,
            "school": school}


def _contracts(deal):
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT * FROM contracts WHERE deal_id = %s ORDER BY id", (deal,))
        return [dict(row) for row in cursor.fetchall()]


def _sale_contracts(deal):
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT contract_id FROM sales WHERE deal_id = %s ORDER BY series_part NULLS FIRST, id", (deal,))
        return [row["contract_id"] for row in cursor.fetchall()]


def _offer_name(slug="consulting"):
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT name FROM offers WHERE slug = %s", (slug,))
        return cursor.fetchone()["name"]


# --- the insert path --------------------------------------------------------

def test_a_sale_without_a_contract_gets_one_titled_by_its_description(world):
    add_deal_sale(world["deal"], "600", date(2026, 11, 2), "Workshop prompt writing", world["first"], status="booked")
    (contract,) = _contracts(world["deal"])
    assert contract["title"] == "Workshop prompt writing" and contract["kind"] == "other"
    assert contract["workspace_id"] == world["first"] and contract["deleted_at"] is None
    assert _sale_contracts(world["deal"]) == [contract["id"]]


def test_a_sale_without_a_description_is_titled_by_its_offer_and_month(world):
    add_deal_sale(world["deal"], "600", date(2026, 11, 2), "   ", world["first"], status="booked")
    (contract,) = _contracts(world["deal"])
    assert contract["title"] == f"{_offer_name()} – 11.2026"


def test_a_four_payment_schedule_shares_one_contract(world):
    add_deal_sale(world["deal"], "2400", date(2026, 11, 8), "English courses", world["first"], status="booked",
                  expected_on=date(2027, 2, 1), months=4)
    (contract,) = _contracts(world["deal"])
    assert contract["title"] == "English courses"
    assert _sale_contracts(world["deal"]) == [contract["id"]] * 4


def test_two_separate_sales_make_two_contracts(world):
    add_deal_sale(world["deal"], "600", date(2026, 11, 2), "First", world["first"], status="booked")
    add_deal_sale(world["deal"], "700", date(2026, 11, 3), "Second", world["first"], status="booked")
    assert [c["title"] for c in _contracts(world["deal"])] == ["First", "Second"]


def test_the_statistics_path_makes_a_contract_too(world):
    add_sale(world["first"], world["school"], "500", date(2026, 11, 2), "Statistics sale", world["deal"], status="booked")
    assert [c["title"] for c in _contracts(world["deal"])] == ["Statistics sale"]


def test_an_existing_contract_of_the_deal_takes_the_payments_and_no_second_one_is_made(world):
    with db() as connection:
        cursor = connection.cursor()
        contract = create_contract(cursor, world["first"], world["deal"], "Year course", "teaching_course")
        ids = insert_sale_payments(cursor, world["first"], world["deal"], Decimal("1200"), date(2026, 11, 2), "ignored",
                                   "booked", date(2027, 1, 1), None, months=3, contract_id=contract)
    assert len(ids) == 3
    (only,) = _contracts(world["deal"])
    assert only["id"] == contract and only["title"] == "Year course" and only["kind"] == "teaching_course"
    assert _sale_contracts(world["deal"]) == [contract] * 3


def test_an_explicit_title_names_the_contract_that_is_made(world):
    with db() as connection:
        insert_sale_payments(connection.cursor(), world["first"], world["deal"], Decimal("100"), date(2026, 11, 2),
                             "a note", "booked", None, None, title="AI for Kaufleute")
    (contract,) = _contracts(world["deal"])
    assert contract["title"] == "AI for Kaufleute"


def test_a_contract_of_another_deal_is_refused_and_nothing_is_written(world):
    with db() as connection:
        foreign = create_contract(connection.cursor(), world["first"], world["other_deal"], "Elsewhere")
    with pytest.raises(ValueError, match="another deal"), db() as connection:
        insert_sale_payments(connection.cursor(), world["first"], world["deal"], Decimal("100"), date(2026, 11, 2),
                             "x", "booked", None, None, contract_id=foreign)
    assert _sale_contracts(world["deal"]) == []
    assert _contracts(world["deal"]) == []


def test_a_deleted_contract_is_refused(world):
    with db() as connection:
        cursor = connection.cursor()
        contract = create_contract(cursor, world["first"], world["deal"], "Gone")
        cursor.execute("UPDATE contracts SET deleted_at = NOW() WHERE id = %s", (contract,))
    with pytest.raises(ValueError, match="deleted"), db() as connection:
        insert_sale_payments(connection.cursor(), world["first"], world["deal"], Decimal("100"), date(2026, 11, 2),
                             "x", "booked", None, None, contract_id=contract)


def test_an_unknown_contract_id_is_refused(world):
    with pytest.raises(ValueError, match="no such contract"), db() as connection:
        insert_sale_payments(connection.cursor(), world["first"], world["deal"], Decimal("100"), date(2026, 11, 2),
                             "x", "booked", None, None, contract_id=987654)


def test_an_unknown_kind_is_refused_before_anything_is_written(world):
    with pytest.raises(ValueError), db() as connection:
        create_contract(connection.cursor(), world["first"], world["deal"], "Bad kind", "speech")
    assert _contracts(world["deal"]) == []


def test_a_blank_title_is_refused(world):
    with pytest.raises(ValueError), db() as connection:
        create_contract(connection.cursor(), world["first"], world["deal"], "   ")


def test_a_refused_schedule_leaves_no_contract_behind(world):
    with pytest.raises(ValueError), db() as connection:
        insert_sale_payments(connection.cursor(), world["first"], world["deal"], Decimal("100"), date(2026, 11, 2),
                             "x", "booked", None, None, months=3)           # a schedule needs the first due day
    assert _contracts(world["deal"]) == []


# --- what the database itself enforces --------------------------------------

def test_the_database_refuses_a_payment_on_a_contract_of_another_deal(world):
    with db() as connection:
        foreign = create_contract(connection.cursor(), world["first"], world["other_deal"], "Elsewhere")
    with pytest.raises(psycopg2.errors.ForeignKeyViolation), db() as connection:
        connection.cursor().execute(
            "INSERT INTO sales (workspace_id, deal_id, contract_id, amount_eur, won_on, status, collected_on) "
            "VALUES (%s, %s, %s, 100, '2026-11-02', 'collected', '2026-11-02')", (world["first"], world["deal"], foreign))


def test_the_database_refuses_a_payment_without_a_contract(world):
    with pytest.raises(psycopg2.errors.NotNullViolation), db() as connection:
        connection.cursor().execute(
            "INSERT INTO sales (workspace_id, deal_id, amount_eur, won_on, status, collected_on) "
            "VALUES (%s, %s, 100, '2026-11-02', 'collected', '2026-11-02')", (world["first"], world["deal"]))


def test_deleting_a_deal_takes_its_contracts_and_payments_with_it(world):
    add_deal_sale(world["other_deal"], "600", date(2026, 11, 2), "Short lived", world["first"], status="booked")
    with db() as connection:
        connection.cursor().execute("DELETE FROM deals WHERE id = %s", (world["other_deal"],))
    assert _contracts(world["other_deal"]) == [] and _sale_contracts(world["other_deal"]) == []


def test_a_contract_of_another_workspace_is_invisible(world):
    with workspace_scope(world["second"]):
        add_deal_sale(world["foreign_deal"], "900", date(2026, 11, 2), "Kessler job", world["second"], status="booked")
    with workspace_scope(world["first"]), db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM contracts")
        assert cursor.fetchall() == []
        cursor.execute("SELECT id FROM sales")
        assert cursor.fetchall() == []
    with workspace_scope(world["second"]), db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT title FROM contracts")
        assert [row["title"] for row in cursor.fetchall()] == ["Kessler job"]


def test_a_workspace_cannot_write_a_contract_on_another_workspaces_deal(world):
    with workspace_scope(world["first"]), pytest.raises(psycopg2.errors.InsufficientPrivilege), db() as connection:
        connection.cursor().execute("INSERT INTO contracts (workspace_id, deal_id, title) VALUES (%s, %s, 'Sneaky')",
                                    (world["first"], world["foreign_deal"]))


def test_a_workspace_cannot_write_a_contract_into_another_workspace(world):
    with workspace_scope(world["first"]), pytest.raises(psycopg2.errors.InsufficientPrivilege), db() as connection:
        connection.cursor().execute("INSERT INTO contracts (workspace_id, deal_id, title) VALUES (%s, %s, 'Sneaky')",
                                    (world["second"], world["deal"]))


def test_a_contract_cannot_name_another_workspaces_person_as_its_contact(world):
    with workspace_scope(world["first"]), pytest.raises(psycopg2.errors.InsufficientPrivilege), db() as connection:
        connection.cursor().execute(
            "INSERT INTO contracts (workspace_id, deal_id, title, contact_person_id) VALUES (%s, %s, 'Sneaky', %s)",
            (world["first"], world["deal"], world["foreign_person"]))


def test_a_contract_can_name_its_own_workspaces_person_and_the_link_rules_hold(world):
    with workspace_scope(world["first"]), db() as connection:
        cursor = connection.cursor()
        cursor.execute("INSERT INTO contracts (workspace_id, deal_id, title, contact_person_id) VALUES (%s, %s, 'Fine', %s) "
                       "RETURNING id", (world["first"], world["deal"], world["coordinator"]))
        contract = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO contract_links (workspace_id, contract_id, label, url) VALUES (%s, %s, 'Syllabus', "
                       "'https://example.org/syllabus') RETURNING id", (world["first"], contract))
        assert cursor.fetchone()["id"]


def test_a_workspace_cannot_attach_a_link_to_another_workspaces_contract(world):
    with workspace_scope(world["second"]):
        add_deal_sale(world["foreign_deal"], "900", date(2026, 11, 2), "Kessler job", world["second"], status="booked")
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM contracts")
        foreign_contract = cursor.fetchone()["id"]
    with workspace_scope(world["first"]), pytest.raises(psycopg2.errors.InsufficientPrivilege), db() as connection:
        connection.cursor().execute("INSERT INTO contract_links (workspace_id, contract_id, label, url) "
                                    "VALUES (%s, %s, 'x', 'https://example.org')", (world["first"], foreign_contract))


@pytest.mark.parametrize("url", ["javascript:alert(1)", "data:text/html,hi", "ftp://example.org/a", "example.org", ""])
def test_the_database_refuses_a_link_that_is_not_http_or_https(world, url):
    with db() as connection:
        contract = create_contract(connection.cursor(), world["first"], world["deal"], "Linked")
    with pytest.raises(psycopg2.errors.CheckViolation), db() as connection:
        connection.cursor().execute("INSERT INTO contract_links (workspace_id, contract_id, label, url) "
                                    "VALUES (%s, %s, 'x', %s)", (world["first"], contract, url))


def test_the_database_refuses_a_blank_label_and_an_overlong_url(world):
    with db() as connection:
        contract = create_contract(connection.cursor(), world["first"], world["deal"], "Linked")
    for label, url in (("   ", "https://example.org"), ("x", "https://example.org/" + "a" * 2000)):
        with pytest.raises(psycopg2.errors.CheckViolation), db() as connection:
            connection.cursor().execute("INSERT INTO contract_links (workspace_id, contract_id, label, url) "
                                        "VALUES (%s, %s, %s, %s)", (world["first"], contract, label, url))
