"""The Organizations, People and Contacts lists filtered by offer, on the real
schema — and the phone's lists, which keep their old meaning unless asked."""
from datetime import date

import pytest
from fastapi.testclient import TestClient

import gcrm.api.main as main
from gcrm.api.auth import require_admin, require_login
from gcrm.api.jwt_auth import create_token
from gcrm.db.connection import db
from gcrm.tools.db_contact_feed import get_contact_feed
from gcrm.tools.db_deals import set_organization_deal
from gcrm.tools.db_organizations import save_organization
from gcrm.tools.db_people import get_people, save_person
from gcrm.tools.db_people_interactions import log_person_note

pytestmark = pytest.mark.integration
PHONE = {"Authorization": f"Bearer {create_token('admin')}"}


@pytest.fixture
def world(clean_database, monkeypatch):
    """A consulting suspect, a language school pitched only LearnWohl, and their people."""
    monkeypatch.setattr("gcrm.tools.db_organizations.geocode", lambda city, country: None)
    monkeypatch.setattr("gcrm.tools.db_people.geocode", lambda city, country: None)
    acme = save_organization("Acme GmbH", "Augsburg", pipeline_stage="suspect", status="ready", source="test_fixture")
    school = save_organization("Simmons Language School", "Hannover", source="test_fixture")
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("UPDATE deals SET deleted_at = NOW() WHERE contact_id = %s", (school,))  # LearnWohl only
        set_organization_deal(cursor, school, stage="prospect", status="contacted", offer="learnwohl")
    ann = save_person("Ann", contact_id=acme, pipeline_stage="prospect", source="test_fixture")
    jamie = save_person("Jamie", contact_id=school, source="test_fixture")
    loner = save_person("Lone Wolf", source="test_fixture")
    for person in (ann, jamie, loner):
        log_person_note(person, "call", "talked")
    with db() as connection:
        connection.cursor().execute("UPDATE people_interactions SET occurred_at = %s", (date(2026, 10, 5),))
    return {"acme": acme, "school": school, "ann": ann, "jamie": jamie, "loner": loner}


@pytest.fixture
def web():
    main.app.dependency_overrides[require_login] = lambda: "admin"
    main.app.dependency_overrides[require_admin] = lambda: "admin"
    yield TestClient(main.app)
    main.app.dependency_overrides.pop(require_login, None)
    main.app.dependency_overrides.pop(require_admin, None)


def test_the_organizations_list_shows_one_pipeline_or_all_of_them(world, web):
    learnwohl = web.get("/organizations/?offer=learnwohl&lang=en").text
    assert "Simmons Language School" in learnwohl and "Acme GmbH" not in learnwohl
    remembered = web.get("/organizations/?lang=en").text  # the choice sticks
    assert "Acme GmbH" not in remembered
    everything = web.get("/organizations/?offer=all&lang=en").text
    assert "Simmons Language School" in everything and "Acme GmbH" in everything
    assert '<span class="deal-offer-label">LearnWohl</span>' in everything
    consulting_suspects = web.get("/organizations/?offer=consulting&stage=suspect&lang=en").text
    assert "Acme GmbH" in consulting_suspects and "Simmons" not in consulting_suspects
    any_prospect = web.get("/organizations/?offer=all&stage=prospect&lang=en").text
    assert "Simmons" in any_prospect and "Acme GmbH" not in any_prospect


def test_the_people_list_lists_everyone_or_one_pipeline(world):
    def names(**kwargs):
        return sorted(p["name"] for p in get_people(**kwargs))
    assert names(offer=None) == ["Ann", "Jamie", "Lone Wolf"]
    assert names(offer="consulting", only_pitched=True) == ["Ann"]
    assert names(offer="consulting", stage="none") == ["Jamie", "Lone Wolf"]
    assert names(offer=None, stage="none") == ["Jamie", "Lone Wolf"]
    assert names(offer=None, stage="prospect") == ["Ann"]
    # the phone's default: Consulting stage, nobody hidden
    assert names() == ["Ann", "Jamie", "Lone Wolf"]


def test_the_contacts_feed_follows_the_offer(world):
    def names(**kwargs):
        rows = get_contact_feed(**kwargs)
        return sorted((r["name"], tuple(d["slug"] for d in r["deals"])) for r in rows)
    assert names(offer=None) == [("Acme GmbH", ("consulting",)), ("Lone Wolf", ()),
                                 ("Simmons Language School", ("learnwohl",))]
    assert names(offer="learnwohl", only_pitched=True) == [("Simmons Language School", ("learnwohl",))]
    assert names(offer=None, stage="prospect") == [("Simmons Language School", ("learnwohl",))]


def test_the_phone_lists_keep_their_old_meaning_unless_asked(world):
    phone = TestClient(main.app)
    default = phone.get("/api/contacts", headers=PHONE).json()
    assert {o["name"]: o["pipeline_stage"] for o in default} == {"Acme GmbH": "suspect",
                                                                "Simmons Language School": None}
    learnwohl = phone.get("/api/contacts?offer=learnwohl", headers=PHONE).json()
    assert [(o["name"], o["pipeline_stage"], o["status"]) for o in learnwohl] == [
        ("Simmons Language School", "prospect", "contacted")]
    everything = phone.get("/api/contacts?offer=all", headers=PHONE).json()
    assert all(o["pipeline_stage"] is None for o in everything) and len(everything) == 2
    assert phone.get("/api/contacts?offer=bogus", headers=PHONE).status_code == 400
    people = phone.get("/api/people", headers=PHONE).json()
    assert len(people) == 3
    feed = phone.get("/api/contact-feed?offer=learnwohl", headers=PHONE).json()
    assert [row["name"] for row in feed] == ["Simmons Language School"]
