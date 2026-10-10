"""Which offer things are about, on the real schema: a new organization or person
entered into a chosen offer's pipeline, log entries tagged with their offer
(picked automatically when there is one open deal), drafts that move their
offer's deal, and the contact counts per offer."""
from datetime import date
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import gcrm.api.main as main
from gcrm.api.auth import require_admin, require_login
from gcrm.api.routers.api_record_edit import OrganizationFields, save_manual_organization
from gcrm.db.connection import db
from gcrm.tools.db_approvals import queue_for_approval
from gcrm.tools.db_contact_counts import get_contact_counts
from gcrm.tools.db_deals import set_organization_deal
from gcrm.tools.db_offers import list_offers
from gcrm.tools.db_organizations import save_organization
from gcrm.tools.db_people import save_person
from gcrm.tools.deal_records import resolve_log_offer

pytestmark = pytest.mark.integration


@pytest.fixture
def offers(clean_database, monkeypatch):
    monkeypatch.setattr("gcrm.tools.db_organizations.geocode", lambda city, country: None)
    monkeypatch.setattr("gcrm.tools.db_people.geocode", lambda city, country: None)
    return {o["slug"]: o["id"] for o in list_offers(None)}


@pytest.fixture
def web():
    main.app.dependency_overrides[require_login] = lambda: "admin"
    main.app.dependency_overrides[require_admin] = lambda: "admin"
    yield TestClient(main.app)
    main.app.dependency_overrides.pop(require_login, None)
    main.app.dependency_overrides.pop(require_admin, None)


def _deals(column: str, owner_id: int) -> list[tuple]:
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute(f"SELECT o.slug, d.pipeline_stage FROM deals d JOIN offers o ON o.id = d.offer_id "
                       f"WHERE d.{column} = %s AND d.deleted_at IS NULL ORDER BY o.slug", (owner_id,))
        return [tuple(row.values()) for row in cursor.fetchall()]


def test_a_school_entered_for_learnwohl_is_not_in_the_consulting_pipeline(offers):
    created = save_manual_organization(
        OrganizationFields(name="Simmons Language School", city="Hannover", pipeline_stage="prospect",
                           offer="learnwohl"), "manual_web")
    assert _deals("contact_id", created["id"]) == [("learnwohl", "prospect")]
    with pytest.raises(Exception) as refused:
        save_manual_organization(OrganizationFields(name="Other", offer="bogus"), "manual_web")
    assert refused.value.status_code == 400


def test_the_web_forms_enter_the_chosen_offer_and_remember_it(offers, web):
    response = web.post("/people/new", data={"name": "Gallery Owner", "pipeline_stage": "suspect",
                                             "offer": "leguild"}, follow_redirects=False)
    person_id = int(response.headers["location"].split("/")[2].split("?")[0])
    assert _deals("person_id", person_id) == [("leguild", "suspect")]
    form = web.get("/organizations/new?lang=en").text
    assert '<option value="leguild" selected>LeGuild.art</option>' in form  # the last one used


def test_a_note_is_about_the_one_open_deal_unless_said_otherwise(offers):
    school = save_organization("School", "Hannover", pipeline_stage="not_in_pipeline", source="test_fixture")
    jamie = save_person("Jamie", contact_id=school, source="test_fixture")
    # only Consulting, and that is closed: nothing open, so general
    assert resolve_log_offer("organization", school, None) is None
    with db() as connection:
        set_organization_deal(connection.cursor(), school, stage="prospect", offer="learnwohl")
    assert resolve_log_offer("organization", school, None) == offers["learnwohl"]
    assert resolve_log_offer("person", jamie, None) == offers["learnwohl"]  # their organization's deal
    with db() as connection:
        set_organization_deal(connection.cursor(), school, stage="candidate", offer="leguild")
    assert resolve_log_offer("organization", school, None) is None  # two open: you pick
    assert resolve_log_offer("organization", school, "0") is None
    assert resolve_log_offer("organization", school, "leguild") == offers["leguild"]
    assert resolve_log_offer("organization", school, str(offers["learnwohl"])) == offers["learnwohl"]
    with pytest.raises(ValueError):
        resolve_log_offer("organization", school, "bogus")


def test_logged_work_carries_its_offer_and_the_page_shows_it(offers, web):
    school = save_organization("School", "Hannover", source="test_fixture")
    jamie = save_person("Jamie", contact_id=school, source="test_fixture")
    web.post(f"/organizations/{school}/activity",
             data={"method": "phone", "note": "LearnWohl demo booked", "offer": str(offers["learnwohl"])})
    web.post(f"/organizations/{school}/activity", data={"method": "phone", "note": "Birthday call", "offer": "0"})
    web.post(f"/people/{jamie}/notes", data={"note": "Sent the trial link", "offer": str(offers["learnwohl"])})
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT summary, offer_id FROM interactions WHERE contact_id = %s ORDER BY id", (school,))
        assert [tuple(r.values()) for r in cursor.fetchall()] == [
            ("LearnWohl demo booked", offers["learnwohl"]), ("Birthday call", None)]
    page = web.get(f"/people/{jamie}?lang=en").text
    assert '<span class="log-offer">LearnWohl</span>' in page


def test_approving_a_draft_moves_its_offers_deal(offers, web):
    acme = save_organization("Acme", "Augsburg", email="info@acme.test", pipeline_stage="suspect",
                             status="ready", source="test_fixture")
    draft = queue_for_approval(acme, 0, "Hallo", "Body")
    with patch("gcrm.tools.email.send_email", return_value=True):
        assert web.post(f"/approvals/{draft}/approve", data={}).status_code == 200
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT o.slug, d.status FROM deals d JOIN offers o ON o.id = d.offer_id "
                       "WHERE d.contact_id = %s", (acme,))
        assert [tuple(r.values()) for r in cursor.fetchall()] == [("consulting", "contacted")]
        cursor.execute("SELECT offer_id FROM interactions WHERE contact_id = %s AND method = 'email'", (acme,))
        assert cursor.fetchone()["offer_id"] == offers["consulting"]


def test_contact_counts_per_offer(offers, web):
    school = save_organization("School", "Hannover", source="test_fixture")
    acme = save_organization("Acme", "Augsburg", source="test_fixture")
    web.post(f"/organizations/{school}/activity",
             data={"method": "phone", "note": "LearnWohl", "offer": str(offers["learnwohl"])})
    web.post(f"/organizations/{acme}/activity", data={"method": "phone", "note": "general", "offer": "0"})
    today = date.today()
    assert get_contact_counts(None, on=today)["month"]["organizations"] == 2
    assert get_contact_counts(None, on=today, offer="learnwohl")["month"]["organizations"] == 1
    assert get_contact_counts(None, on=today, offer="consulting")["month"]["organizations"] == 0
