"""The Deals panel's and the Offers page's data against the real schema: adding,
moving and removing deals, contact people, next steps in the owner's log, and
managing offers."""
from datetime import date

import pytest

from gcrm.db.connection import db
from gcrm.tools.db_offers import (
    create_offer,
    list_offers,
    move_offer,
    set_offer_archived,
    update_offer,
)
from gcrm.tools.db_organizations import save_organization
from gcrm.tools.db_people import save_person
from gcrm.tools.deal_records import (
    DealNotFound,
    add_deal,
    get_deals,
    get_deals_as_contact_person,
    remove_deal,
    set_deal_next_step,
    update_deal,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def school(clean_database, monkeypatch):
    monkeypatch.setattr("gcrm.tools.db_organizations.geocode", lambda city, country: None)
    monkeypatch.setattr("gcrm.tools.db_people.geocode", lambda city, country: None)
    contact_id = save_organization("Simmons Language School", "Hannover", pipeline_stage="not_in_pipeline",
                                   status="not_interested", source="test_fixture")
    jamie = save_person("Jamie Simmons", contact_id=contact_id, source="test_fixture")
    offers = {o["slug"]: o["id"] for o in list_offers(None, include_archived=True)}
    return {"contact_id": contact_id, "jamie": jamie, "offers": offers}


def _log(table: str, column: str, owner_id: int) -> list[tuple]:
    text = "note" if table == "people_interactions" else "summary"
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute(f"SELECT method, {text} AS text, o.slug FROM {table} t "
                       f"LEFT JOIN offers o ON o.id = t.offer_id WHERE t.{column} = %s ORDER BY t.id", (owner_id,))
        return [tuple(row.values()) for row in cursor.fetchall()]


def test_pitching_learnwohl_to_a_school_that_said_no_to_consulting(school):
    deal_id = add_deal("organization", school["contact_id"], school["offers"]["learnwohl"])
    assert add_deal("organization", school["contact_id"], school["offers"]["learnwohl"]) == deal_id  # once

    update_deal(deal_id, stage="prospect", status="contacted", contact_person_id=school["jamie"])

    deals = get_deals("organization", school["contact_id"])
    assert [(d["offer_slug"], d["pipeline_stage"], d["status"], d["contact_person_name"]) for d in deals] == [
        ("consulting", "not_in_pipeline", "not_interested", None),
        ("learnwohl", "prospect", "contacted", "Jamie Simmons")]
    [as_contact] = get_deals_as_contact_person(school["jamie"])
    assert (as_contact["organization_name"], as_contact["offer_slug"]) == ("Simmons Language School", "learnwohl")


def test_a_contact_person_must_work_there_and_only_organizations_have_one(school):
    stranger = save_person("Someone Else", source="test_fixture")
    deal_id = add_deal("organization", school["contact_id"], school["offers"]["learnwohl"])
    with pytest.raises(ValueError):
        update_deal(deal_id, contact_person_id=stranger)
    own = add_deal("person", stranger, school["offers"]["leguild"])
    with pytest.raises(ValueError):
        update_deal(own, contact_person_id=school["jamie"])
    assert update_deal(deal_id, contact_person_id=None)["contact_person_id"] is None


def test_archived_offers_and_other_workspaces_cannot_be_pitched(school):
    set_offer_archived(None, school["offers"]["notes-world"], True)  # offers outlive clean_database
    try:
        with pytest.raises(DealNotFound):
            add_deal("person", school["jamie"], school["offers"]["notes-world"])
    finally:
        set_offer_archived(None, school["offers"]["notes-world"], False)
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("DELETE FROM workspaces WHERE slug = 'deal-records-other'")
        cursor.execute("INSERT INTO workspaces (name, slug) VALUES ('Other', 'deal-records-other') RETURNING id")
        other = cursor.fetchone()["id"]
    try:
        deal_id = add_deal("person", school["jamie"], school["offers"]["leguild"])
        with pytest.raises(DealNotFound):
            update_deal(deal_id, other, stage="customer")
        with pytest.raises(DealNotFound):
            add_deal("person", school["jamie"], school["offers"]["learnwohl"], workspace_id=other)
    finally:
        with db() as connection:
            connection.cursor().execute("DELETE FROM workspaces WHERE id = %s", (other,))


def test_next_steps_go_to_the_owners_log_with_the_offer(school):
    org_deal = add_deal("organization", school["contact_id"], school["offers"]["learnwohl"])
    person_deal = add_deal("person", school["jamie"], school["offers"]["leguild"])

    set_deal_next_step(org_deal, "Demo for the teachers", date(2026, 10, 20))
    assert set_deal_next_step(org_deal, " Demo for the teachers ", date(2026, 10, 20))["logged"] is False
    set_deal_next_step(org_deal, "", None)
    set_deal_next_step(person_deal, "Send the gallery link", None)

    assert _log("interactions", "contact_id", school["contact_id"]) == [
        ("next_step", "Demo for the teachers (2026-10-20)", "learnwohl"),
        ("next_step_done", "✓ Demo for the teachers", "learnwohl")]
    assert _log("people_interactions", "person_id", school["jamie"]) == [
        ("next_step", "Send the gallery link", "leguild")]
    with pytest.raises(ValueError):
        set_deal_next_step(org_deal, "", date(2026, 10, 20))


def test_removing_a_deal_keeps_it_out_of_the_panel_and_lets_it_be_added_again(school):
    deal_id = add_deal("organization", school["contact_id"], school["offers"]["learnwohl"])
    remove_deal(deal_id)
    assert [d["offer_slug"] for d in get_deals("organization", school["contact_id"])] == ["consulting"]
    assert add_deal("organization", school["contact_id"], school["offers"]["learnwohl"]) != deal_id
    with pytest.raises(DealNotFound):
        remove_deal(deal_id)


@pytest.fixture
def scratch_offers(clean_database):
    """Offers this test adds; removed afterwards, because clean_database keeps offers."""
    created: list[int] = []
    yield created
    with db() as connection:
        connection.cursor().execute("DELETE FROM offers WHERE id = ANY(%s)", (created,))


def test_offers_are_added_renamed_reordered_and_archived(scratch_offers):
    first = create_offer(None, "Workshops", "https://example.test", "one_off")
    second = create_offer(None, "Workshops", "", "subscription")  # same name, its own slug
    scratch_offers += [first, second]
    slugs = {o["id"]: o["slug"] for o in list_offers(None)}
    assert (slugs[first], slugs[second]) == ("workshops", "workshops-2")

    assert update_offer(None, first, "Team workshops", "", "subscription")
    move_offer(None, second, "up")
    names = [o["name"] for o in list_offers(None)]
    assert names[-2:] == ["Workshops", "Team workshops"]

    set_offer_archived(None, first, True)
    assert "Team workshops" not in [o["name"] for o in list_offers(None)]
    assert [o["archived"] for o in list_offers(None, include_archived=True) if o["id"] == first] == [True]
    with pytest.raises(ValueError):
        create_offer(None, "  ")
