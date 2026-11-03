"""Map pins against the real schema: recording is repeatable, a removed pin can be pinned
again, two companies can share one place, and the list filter and the not-yet-pinned query
see the difference."""
import pytest
from fastapi.testclient import TestClient

import gcrm.api.main as main
from gcrm.api.auth import require_login
from gcrm.api.routers.organizations import _build_organization_filters, _fetch_organizations_page
from gcrm.db.connection import db
from gcrm.tools.map_pins import (
    COLD_CALL_CANDIDATES,
    candidates_not_on_map,
    pins_for_contact,
    record_pin,
    remove_pin,
)

pytestmark = pytest.mark.integration

PLACE_A = "0x479c1f7973ddb70b:0x3456fcf4696e45ec"
PLACE_B = "0x479c202e9bceb9ad:0x3844f476c6c2d973"


@pytest.fixture
def two_candidates(clean_database):
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM workspaces WHERE slug = 'default'")
        workspace_id = cur.fetchone()["id"]
        ids = []
        for name, lat in (("ASP Dichtstoffe GmbH", 48.1649), ("Auto Frey GmbH", 48.1725)):
            cur.execute(
                "INSERT INTO contacts (name, city, latitude, longitude, workspace_id) "
                "VALUES (%s, 'Untermeitingen', %s, 10.83, %s) RETURNING id", (name, lat, workspace_id))
            contact_id = cur.fetchone()["id"]
            cur.execute(
                "INSERT INTO deals (workspace_id, offer_id, contact_id, pipeline_stage, status) "
                "VALUES (%s, offer_id_for(%s, 'consulting'), %s, 'candidate', 'none')",
                (workspace_id, workspace_id, contact_id))
            ids.append(contact_id)
    return {"workspace_id": workspace_id, "ids": ids}


def test_recording_a_pin_is_repeatable_and_keeps_the_first_saved_time(two_candidates):
    first_id = two_candidates["ids"][0]
    first = record_pin(first_id, PLACE_A, "ASP Dichtstoffe GmbH", maps_address="Schwabenstraße 50",
                       maps_url="https://www.google.com/maps/place/x", note="first note")
    again = record_pin(first_id, PLACE_A, "ASP Dichtstoffe GmbH", maps_address="Schwabenstraße 50, Untermeitingen",
                       note="second note")
    assert again["id"] == first["id"] and again["saved_at"] == first["saved_at"]
    assert again["note"] == "second note" and again["maps_address"].endswith("Untermeitingen")
    assert len(pins_for_contact(first_id)) == 1
    assert first["list_name"] == COLD_CALL_CANDIDATES and first["workspace_id"] == two_candidates["workspace_id"]


def test_an_unknown_organization_gets_no_pin(two_candidates):
    assert record_pin(999999, PLACE_A, "Nobody") is None


def test_a_removed_pin_stays_on_record_and_can_be_pinned_again(two_candidates):
    contact_id = two_candidates["ids"][0]
    pin = record_pin(contact_id, PLACE_A, "ASP Dichtstoffe GmbH")
    assert remove_pin(pin["id"]) is True and remove_pin(pin["id"]) is False
    assert pins_for_contact(contact_id) == []
    again = record_pin(contact_id, PLACE_A, "ASP Dichtstoffe GmbH")
    assert again["id"] != pin["id"]
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT count(*) AS n FROM map_pins WHERE contact_id = %s", (contact_id,))
        assert cur.fetchone()["n"] == 2


def test_two_companies_can_share_one_place_and_one_company_can_have_two_lists(two_candidates):
    a, b = two_candidates["ids"]
    record_pin(a, PLACE_B, "Shared building")
    record_pin(b, PLACE_B, "Shared building")
    record_pin(a, PLACE_B, "Shared building", list_name="Cold calls visited, left info")
    assert len(pins_for_contact(a)) == 2 and len(pins_for_contact(b)) == 1


def test_candidates_not_on_map_shrinks_as_pins_are_recorded(two_candidates):
    a, b = two_candidates["ids"]
    workspace_id = two_candidates["workspace_id"]
    assert [c["id"] for c in candidates_not_on_map(workspace_id)] == [a, b]
    record_pin(a, PLACE_A, "ASP Dichtstoffe GmbH")
    assert [c["id"] for c in candidates_not_on_map(workspace_id)] == [b]
    remove_pin(pins_for_contact(a)[0]["id"])
    assert [c["id"] for c in candidates_not_on_map(workspace_id)] == [a, b]


def test_do_not_contact_and_contacted_organizations_are_not_candidates_for_the_map(two_candidates):
    a, b = two_candidates["ids"]
    with db() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE contacts SET do_not_contact = TRUE WHERE id = %s", (a,))
        cur.execute("INSERT INTO interactions (contact_id, interaction_date, method, direction, summary) "
                    "VALUES (%s, CURRENT_DATE, 'in_person', 'outbound', 'visited')", (b,))
    assert candidates_not_on_map(two_candidates["workspace_id"]) == []


def test_the_organizations_list_filters_and_marks_pinned_ones(two_candidates):
    a, b = two_candidates["ids"]
    record_pin(a, PLACE_A, "ASP Dichtstoffe GmbH")
    for on_map, expected in (("1", [a]), ("0", [b]), ("", [a, b])):
        where, params = _build_organization_filters("", "", "", "", workspace_id=two_candidates["workspace_id"],
                                                    on_map=on_map)
        rows = _fetch_organizations_page(where, params, "c.id", "ASC", 0, None, two_candidates["workspace_id"])[0]
        assert [r["id"] for r in rows] == expected
        for row in rows:
            assert row["map_pin_count"] == (1 if row["id"] == a else 0)


def test_the_pages_show_the_pin_and_the_filter(two_candidates):
    a, b = two_candidates["ids"]
    record_pin(a, PLACE_A, "ASP Dichtstoffe GmbH", maps_address="Schwabenstraße 50, Untermeitingen",
               maps_url="https://www.google.com/maps/place/ASP+Dichtstoffe+GmbH", note="Maps address checked")
    main.app.dependency_overrides[require_login] = lambda: "admin"
    try:
        client = TestClient(main.app)
        with client:
            client.cookies.clear()
            detail_a = client.get(f"/organizations/{a}")
            detail_b = client.get(f"/organizations/{b}")
            on_map = client.get("/organizations/?on_map=1")
            off_map = client.get("/organizations/?on_map=0")
    finally:
        main.app.dependency_overrides.pop(require_login, None)
    for page in (detail_a, detail_b, on_map, off_map):
        assert page.status_code == 200, page.text[:500]
    assert "Schwabenstraße 50, Untermeitingen" in detail_a.text and "Maps address checked" in detail_a.text
    assert "https://www.google.com/maps/place/ASP+Dichtstoffe+GmbH" in detail_a.text
    assert "Not pinned on any Google Maps list yet." in detail_b.text
    assert "ASP Dichtstoffe GmbH" in on_map.text and "Auto Frey GmbH" not in on_map.text
    assert "Auto Frey GmbH" in off_map.text and "ASP Dichtstoffe GmbH" not in off_map.text
    assert 'class="badge map-badge"' in on_map.text and 'class="badge map-badge"' not in off_map.text
