"""Offers and deals against the real schema (migration 064): the stage lives on a
deal per offer, the rules the table enforces, and a rollback that loses nothing."""
import sys
from pathlib import Path
from subprocess import run

import psycopg2
import pytest

from gcrm.db.connection import db
from gcrm.tools.db_deals import set_organization_deal, set_person_stage
from gcrm.tools.db_organizations import get_organization, save_organization, set_organization_state
from gcrm.tools.db_people import save_person, set_person_pipeline_stage
from gcrm.tools.people_next_step import set_person_next_step
from gcrm.tools.privacy_retention import erase_organization, erase_person

pytestmark = pytest.mark.integration

ROOT = Path(__file__).parents[2]


@pytest.fixture
def no_geocoding(monkeypatch):
    monkeypatch.setattr("gcrm.tools.db_organizations.geocode", lambda city, country: None)
    monkeypatch.setattr("gcrm.tools.db_people.geocode", lambda city, country: None)


def _workspace() -> int:
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug = 'default'")
        return cursor.fetchone()["id"]


def _deals(**owner) -> list[tuple]:
    (column, value), = owner.items()
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT o.slug, d.pipeline_stage, d.status, d.next_step FROM deals d "
            f"JOIN offers o ON o.id = d.offer_id WHERE d.{column} = %s AND d.deleted_at IS NULL ORDER BY o.slug",
            (value,),
        )
        return [tuple(row.values()) for row in cursor.fetchall()]


def test_the_default_workspace_sells_consulting_and_the_three_apps(clean_database):
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT slug, revenue_kind FROM offers WHERE workspace_id = %s ORDER BY sort_order",
                       (_workspace(),))
        assert [tuple(r.values()) for r in cursor.fetchall()] == [
            ("consulting", "one_off"), ("learnwohl", "subscription"),
            ("leguild", "subscription"), ("notes-world", "subscription")]


def test_a_new_workspace_gets_consulting_by_itself(clean_database):
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("DELETE FROM workspaces WHERE slug = 'deals-new-workspace'")
        cursor.execute("INSERT INTO workspaces (name, slug) VALUES ('New', 'deals-new-workspace') RETURNING id")
        workspace = cursor.fetchone()["id"]
        cursor.execute("SELECT slug FROM offers WHERE workspace_id = %s", (workspace,))
        assert [r["slug"] for r in cursor.fetchall()] == ["consulting"]
        cursor.execute("DELETE FROM workspaces WHERE id = %s", (workspace,))


def test_an_organization_enters_the_consulting_pipeline_and_moves_on_its_deal(clean_database, no_geocoding):
    acme = save_organization("Acme", "Augsburg", pipeline_stage="suspect", status="ready", source="test_fixture")
    assert _deals(contact_id=acme) == [("consulting", "suspect", "ready", None)]

    set_organization_state(acme, pipeline_stage="opportunity", status="proposal")

    organization = get_organization(acme)
    assert (organization["pipeline_stage"], organization["status"]) == ("opportunity", "proposal")
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT entity_type, entity_id, from_stage, to_stage, offer_id IS NOT NULL AS has_offer, "
                       "deal_id IS NOT NULL AS has_deal FROM stage_changes")
        assert [tuple(r.values()) for r in cursor.fetchall()] == [
            ("organization", acme, "suspect", "opportunity", True, True)]


def test_another_offer_has_its_own_stage(clean_database, no_geocoding):
    school = save_organization("Simmons Language School", "Hannover", pipeline_stage="not_in_pipeline",
                               status="dropped", source="test_fixture")
    with db() as connection:
        set_organization_deal(connection.cursor(), school, stage="prospect", offer="learnwohl")

    assert _deals(contact_id=school) == [("consulting", "not_in_pipeline", "dropped", None),
                                         ("learnwohl", "prospect", "none", None)]
    # everything that reads "the" stage today reads Consulting's
    assert get_organization(school)["pipeline_stage"] == "not_in_pipeline"


def test_one_live_deal_per_offer_and_exactly_one_owner(clean_database, no_geocoding):
    acme = save_organization("Acme", "Augsburg", source="test_fixture")
    person = save_person("Ann", source="test_fixture")
    workspace = _workspace()
    insert = ("INSERT INTO deals (workspace_id, offer_id, contact_id, person_id) "
              "VALUES (%s, offer_id_for(%s, 'consulting'), %s, %s)")
    for owner, error in (((acme, None), psycopg2.errors.UniqueViolation),   # a second live one
                         ((acme, person), psycopg2.errors.CheckViolation),  # two owners
                         ((None, None), psycopg2.errors.CheckViolation)):   # no owner
        with pytest.raises(error), db() as connection:
            connection.cursor().execute(insert, (workspace, workspace, *owner))
    with db() as connection:  # once the old one is deleted, a new one is fine
        cursor = connection.cursor()
        cursor.execute("UPDATE deals SET deleted_at = NOW() WHERE contact_id = %s", (acme,))
        cursor.execute(insert, (workspace, workspace, acme, None))


def test_clearing_a_persons_stage_removes_the_deal_unless_a_next_step_needs_it(clean_database, no_geocoding):
    plain = save_person("Ann", pipeline_stage="prospect", allow_duplicate=True, source="test_fixture")
    planned = save_person("Bob", pipeline_stage="prospect", allow_duplicate=True, source="test_fixture")
    set_person_next_step(planned, "Call on Friday", None)

    assert set_person_pipeline_stage(plain, None) == (True, None)
    assert set_person_pipeline_stage(planned, "") == (True, "candidate")
    assert set_person_pipeline_stage(999999, "prospect") == (False, None)

    assert _deals(person_id=plain) == []
    assert _deals(person_id=planned) == [("consulting", "candidate", "none", "Call on Friday")]
    with pytest.raises(ValueError), db() as connection:
        set_person_stage(connection.cursor(), plain, "bogus")


def test_erasing_takes_the_deals_with_it_and_a_contact_person_is_only_unnamed(clean_database, no_geocoding):
    acme = save_organization("Acme", "Augsburg", source="test_fixture")
    ann = save_person("Ann", pipeline_stage="prospect", source="test_fixture")
    with db() as connection:
        connection.cursor().execute("UPDATE deals SET contact_person_id = %s WHERE contact_id = %s", (ann, acme))

    erase_person(ann, suppress_reimport=False)
    assert _deals(person_id=ann) == []
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT contact_person_id FROM deals WHERE contact_id = %s", (acme,))
        assert cursor.fetchone()["contact_person_id"] is None

    erase_organization(acme)
    assert _deals(contact_id=acme) == []


def test_the_rollback_restores_every_stage_and_the_migration_rebuilds_the_deals(clean_database, no_geocoding):
    """scripts/rollback_064_offers_and_deals.sql, then the migration again: the
    old columns get every stage change made since the deploy, and re-applying
    064 turns them back into the same Consulting deals."""
    acme = save_organization("Acme", "Augsburg", pipeline_stage="suspect", status="ready", source="test_fixture")
    shop = save_organization("Shop", "Ulm", pipeline_stage="customer", source="test_fixture")
    staged = save_person("Ann", pipeline_stage="prospect", allow_duplicate=True, source="test_fixture")
    planned = save_person("Bob", allow_duplicate=True, source="test_fixture")
    plain = save_person("Cy", allow_duplicate=True, source="test_fixture")
    set_person_next_step(staged, "Send portfolio", None)
    set_person_next_step(planned, "Coffee", None)
    set_organization_state(acme, pipeline_stage="prospect", status="contacted")  # a change after the deploy

    try:
        with db() as connection:
            connection.cursor().execute((ROOT / "scripts" / "rollback_064_offers_and_deals.sql").read_text())
        with db() as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT id, pipeline_stage, status FROM contacts ORDER BY id")
            assert [tuple(r.values()) for r in cursor.fetchall()] == [
                (acme, "prospect", "contacted"), (shop, "customer", "none")]
            cursor.execute("SELECT id, pipeline_stage, next_step FROM people ORDER BY id")
            assert [tuple(r.values()) for r in cursor.fetchall()] == [
                (staged, "prospect", "Send portfolio"), (planned, "candidate", "Coffee"), (plain, None, None)]
            cursor.execute("SELECT to_regclass('deals') IS NULL AS gone")
            assert cursor.fetchone()["gone"]
    finally:
        run([sys.executable, "scripts/migrate.py"], cwd=ROOT, check=True)

    assert _deals(contact_id=acme) == [("consulting", "prospect", "contacted", None)]
    assert _deals(contact_id=shop) == [("consulting", "customer", "none", None)]
    assert _deals(person_id=staged) == [("consulting", "prospect", "none", "Send portfolio")]
    assert _deals(person_id=planned) == [("consulting", "candidate", "none", "Coffee")]
    assert _deals(person_id=plain) == []
