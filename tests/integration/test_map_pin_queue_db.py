"""The pin step against the real schema (plan 2026-11-05, step 5): the queue of companies
waiting to be pinned, optionally only a Gather run's; the latest Gather run's companies;
and recording what the browser loop found, filling only blank fields."""
import pytest

from gcrm.db.connection import db
from gcrm.tools.db_agent_runs import finish_run, start_run
from gcrm.tools.map_pins import (
    apply_pin_result,
    latest_gather_ids,
    pin_queue,
    pins_for_contact,
    record_pin,
)

pytestmark = pytest.mark.integration


def add_company(name: str, stage: str = "candidate", **columns) -> tuple[int, int]:
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM workspaces WHERE slug = 'default'")
        workspace_id = cur.fetchone()["id"]
        names = ", ".join(["name", "city", "workspace_id", *columns])
        marks = ", ".join(["%s"] * (3 + len(columns)))
        cur.execute(f"INSERT INTO contacts ({names}) VALUES ({marks}) RETURNING id",
                    (name, "Untermeitingen", workspace_id, *columns.values()))
        contact_id = cur.fetchone()["id"]
        cur.execute("INSERT INTO deals (workspace_id, offer_id, contact_id, pipeline_stage, status) "
                    "VALUES (%s, offer_id_for(%s, 'consulting'), %s, %s, 'none')",
                    (workspace_id, workspace_id, contact_id, stage))
    return workspace_id, contact_id


def test_the_queue_can_be_limited_to_a_gather_runs_companies(clean_database):
    workspace_id, new = add_company("Meile GmbH", latitude=48.16, longitude=10.8)
    _, older = add_company("Faist Systeme GmbH", address="Daimlerstraße 3, 86836 Untermeitingen")
    assert {row["id"] for row in pin_queue(workspace_id)} == {new, older}
    assert [row["id"] for row in pin_queue(workspace_id, ids=[new])] == [new]


def test_the_queue_skips_pinned_do_not_contact_and_placeless_companies(clean_database):
    workspace_id, pinned = add_company("Meile GmbH", latitude=48.16, longitude=10.8)
    add_company("Halbich", latitude=48.1, longitude=10.7, do_not_contact=True)
    add_company("Nowhere GmbH")
    record_pin(pinned, "0x1:0x1", "Meile GmbH")
    assert pin_queue(workspace_id) == []


def test_the_latest_gather_runs_companies_are_found(clean_database):
    older = start_run("gather", {})
    finish_run(older, "completed", "older", {"saved_ids": [1, 2]})
    newer = start_run("gather", {})
    finish_run(newer, "completed", "newer", {"saved_ids": [5, 6, 7]})
    assert latest_gather_ids() == [5, 6, 7]


def test_a_saved_result_is_recorded_and_fills_only_blank_fields(clean_database):
    _, contact_id = add_company("Meile GmbH", phone="08232 1234")
    outcome = apply_pin_result({
        "id": contact_id, "status": "saved", "key": "0x479c1f7973ddb70b:0x3456fcf4696e45ec",
        "title": "Meile GmbH", "address": "Siemensstraße 21, 86836 Untermeitingen", "phone": "08232 9999",
        "website": "http://www.meile-gruppe.de/", "lat": 48.1649, "lon": 10.83, "dist": 120,
    })
    assert outcome == "pinned"
    assert [pin["maps_name"] for pin in pins_for_contact(contact_id)] == ["Meile GmbH"]
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT address, phone, website, latitude FROM contacts WHERE id = %s", (contact_id,))
        row = cur.fetchone()
    assert row["address"] == "Siemensstraße 21, 86836 Untermeitingen"
    assert row["phone"] == "08232 1234"  # kept, not replaced
    assert row["website"] == "http://www.meile-gruppe.de/" and row["latitude"] == 48.1649


def test_results_that_were_not_saved_on_the_map_record_nothing(clean_database):
    _, contact_id = add_company("Auto Frey GmbH")
    for status in ("name_mismatch", "too_far", "closed", "no_match", "unverified"):
        assert apply_pin_result({"id": contact_id, "status": status, "key": "0x1:0x2", "title": "x"}) == f"skipped: {status}"
    assert pins_for_contact(contact_id) == []


def test_a_malformed_place_key_is_refused(clean_database):
    _, contact_id = add_company("Meile GmbH")
    assert apply_pin_result({"id": contact_id, "status": "saved", "key": "0x1:0x2; DROP", "title": "Meile"}) == "bad key"
    assert pins_for_contact(contact_id) == []
