"""Follow-ups remain independent and scoped to their owner."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import psycopg2
import pytest

from gcrm.db.connection import db
from gcrm.tools.db_deals import set_person_stage
from gcrm.tools.db_organizations import save_organization
from gcrm.tools.deal_records import get_deals, set_deal_next_step
from gcrm.tools.follow_ups import (
    change_follow_up_status,
    create_follow_up,
    list_follow_ups,
    resolve_review,
    update_follow_up,
)
from gcrm.tools.privacy_retention import erase_organization, erase_person
from gcrm.workspace_context import workspace_scope

pytestmark = pytest.mark.integration


def test_legacy_edit_and_completion_change_only_earliest_task(clean_database, monkeypatch):
    monkeypatch.setattr("gcrm.tools.db_organizations.geocode", lambda city, country: None)
    organization = save_organization("Example GmbH", "Augsburg", source="test_fixture")
    deal = get_deals("organization", organization)[0]
    first = create_follow_up(deal_id=deal["id"], task_type="commitment", task_text="Send proposal",
                             due_date=date(2026, 12, 1))
    second = create_follow_up(deal_id=deal["id"], task_type="check_in", task_text="Call back",
                              due_date=date(2026, 12, 10))

    set_deal_next_step(deal["id"], "Send revised proposal", date(2026, 12, 2))
    set_deal_next_step(deal["id"], "", None)
    tasks = list_follow_ups()

    assert [(task["id"], task["task_text"]) for task in tasks] == [(second, "Call back")]
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT status FROM follow_ups WHERE id=%s", (first,))
        assert cursor.fetchone()["status"] == "completed"


def test_typed_legacy_capture_creates_an_active_follow_up(clean_database, monkeypatch):
    monkeypatch.setattr("gcrm.tools.db_organizations.geocode", lambda city, country: None)
    organization = save_organization("Example GmbH", "Augsburg", source="test_fixture")
    deal = get_deals("organization", organization)[0]
    set_deal_next_step(deal["id"], "Send details", None, task_type="commitment")
    repeated = set_deal_next_step(deal["id"], "Send details", None, task_type="commitment")
    assert repeated["logged"] is False
    assert [(task["task_text"], task["task_type"]) for task in list_follow_ups()] == [
        ("Send details", "commitment")]


def test_concurrent_edits_detect_stale_version(clean_database, monkeypatch):
    monkeypatch.setattr("gcrm.tools.db_organizations.geocode", lambda city, country: None)
    organization = save_organization("Example GmbH", "Augsburg", source="test_fixture")
    deal = get_deals("organization", organization)[0]
    task_id = create_follow_up(deal_id=deal["id"], task_type="check_in", task_text="Call")
    version = list_follow_ups()[0]["updated_at"]
    update_follow_up(task_id, task_type="check_in", task_text="Call Monday", due_date=None, version=version)
    with pytest.raises(ValueError, match="changed"):
        update_follow_up(task_id, task_type="check_in", task_text="Call Tuesday", due_date=None, version=version)


def test_simultaneous_edits_do_not_overwrite_each_other(clean_database, monkeypatch):
    monkeypatch.setattr("gcrm.tools.db_organizations.geocode", lambda city, country: None)
    organization = save_organization("Example GmbH", "Augsburg", source="test_fixture")
    deal = get_deals("organization", organization)[0]
    task_id = create_follow_up(deal_id=deal["id"], task_type="check_in", task_text="Call")
    version = list_follow_ups()[0]["updated_at"]

    def edit(text):
        try:
            update_follow_up(task_id, task_type="check_in", task_text=text, due_date=None, version=version)
            return "saved"
        except ValueError:
            return "stale"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(edit, ["Call Monday", "Call Tuesday"]))
    assert sorted(outcomes) == ["saved", "stale"]


def test_dismiss_and_complete_are_distinct_and_do_not_change_siblings(clean_database, monkeypatch):
    monkeypatch.setattr("gcrm.tools.db_organizations.geocode", lambda city, country: None)
    organization = save_organization("Example GmbH", "Augsburg", source="test_fixture")
    deal = get_deals("organization", organization)[0]
    first = create_follow_up(deal_id=deal["id"], task_type="commitment", task_text="Send details")
    second = create_follow_up(deal_id=deal["id"], task_type="check_in", task_text="Call")
    rows = list_follow_ups()
    change_follow_up_status(first, "dismissed", rows[0]["updated_at"])
    assert [row["id"] for row in list_follow_ups()] == [second]
    change_follow_up_status(second, "completed", rows[1]["updated_at"])
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT status, completed_at IS NOT NULL AS completed, dismissed_at IS NOT NULL AS dismissed "
                       "FROM follow_ups ORDER BY id")
        assert [tuple(row.values()) for row in cursor.fetchall()] == [
            ("dismissed", False, True), ("completed", True, False)]


def test_workspace_role_can_read_own_tasks(clean_database, monkeypatch):
    monkeypatch.setattr("gcrm.tools.db_organizations.geocode", lambda city, country: None)
    organization = save_organization("Example GmbH", "Augsburg", source="test_fixture")
    deal = get_deals("organization", organization)[0]
    create_follow_up(deal_id=deal["id"], task_type="check_in", task_text="Call")
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT workspace_id FROM deals WHERE id=%s", (deal["id"],))
        workspace_id = cursor.fetchone()["workspace_id"]
        cursor.execute("SELECT set_config('app.workspace_id', %s, TRUE)", (str(workspace_id),))
        cursor.execute("SET LOCAL ROLE engcrm_workspace")
        cursor.execute("SELECT task_text FROM follow_ups")
        assert [row["task_text"] for row in cursor.fetchall()] == ["Call"]
        cursor.execute("INSERT INTO follow_ups (workspace_id, contact_id, task_type, task_text, status) "
                       "VALUES (%s,%s,'commitment','Send details','active')", (workspace_id, organization))


def test_general_follow_up_has_no_invented_deal(clean_database, monkeypatch):
    monkeypatch.setattr("gcrm.tools.db_organizations.geocode", lambda city, country: None)
    organization = save_organization("Example GmbH", "Augsburg", source="test_fixture")
    task_id = create_follow_up(contact_id=organization, task_type="commitment", task_text="Send details")
    task = list_follow_ups()[0]
    assert (task["id"], task["contact_id"], task["deal_id"]) == (task_id, organization, None)
    deal = get_deals("organization", organization)[0]
    update_follow_up(task_id, task_type="commitment", task_text="Send details", due_date=None,
                     version=task["updated_at"], deal_id=deal["id"])
    assert list_follow_ups()[0]["deal_id"] == deal["id"]


def test_workspace_cannot_link_a_foreign_owner(clean_database):
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug='default'")
        local_workspace = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO workspaces (name, slug) VALUES ('Other follow-ups', 'followups-other') "
                       "ON CONFLICT (slug) DO UPDATE SET name=EXCLUDED.name RETURNING id")
        foreign_workspace = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO contacts (name, workspace_id) VALUES ('Foreign', %s) RETURNING id",
                       (foreign_workspace,))
        foreign_organization = cursor.fetchone()["id"]
    with pytest.raises(psycopg2.errors.InsufficientPrivilege), db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT set_config('app.workspace_id', %s, TRUE)", (str(local_workspace),))
        cursor.execute("SET LOCAL ROLE engcrm_workspace")
        cursor.execute("INSERT INTO follow_ups (workspace_id, contact_id, task_type, task_text, status) "
                       "VALUES (%s,%s,'commitment','Send details','active')", (local_workspace, foreign_organization))


def test_workspace_cannot_read_or_modify_another_workspaces_task(clean_database, monkeypatch):
    monkeypatch.setattr("gcrm.tools.db_organizations.geocode", lambda city, country: None)
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug='default'")
        local_workspace = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO workspaces (name, slug) VALUES ('Other follow-ups', 'followups-other') "
                       "ON CONFLICT (slug) DO UPDATE SET name=EXCLUDED.name RETURNING id")
        foreign_workspace = cursor.fetchone()["id"]
    with workspace_scope(foreign_workspace):
        organization = save_organization("Foreign GmbH", "Augsburg", source="test_fixture")
        foreign_id = create_follow_up(contact_id=organization, task_type="commitment", task_text="Private")
        version = list_follow_ups()[0]["updated_at"]
    with workspace_scope(local_workspace):
        assert list_follow_ups() == []
        with pytest.raises(ValueError, match="unavailable"):
            change_follow_up_status(foreign_id, "completed", version)
        with pytest.raises(ValueError, match="Owner not found"):
            create_follow_up(contact_id=organization, task_type="commitment", task_text="Wrong owner")
    with workspace_scope(foreign_workspace):
        assert [task["task_text"] for task in list_follow_ups()] == ["Private"]


def test_erasure_does_not_fail_on_related_follow_ups(clean_database, monkeypatch):
    from gcrm.tools.db_people import save_person

    monkeypatch.setattr("gcrm.tools.db_organizations.geocode", lambda city, country: None)
    organization = save_organization("Example GmbH", "Augsburg", source="test_fixture")
    person = save_person("Anna Example", source="test_fixture", contact_id=organization, geocode_city=False)
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT workspace_id FROM contacts WHERE id=%s", (organization,))
        workspace_id = cursor.fetchone()["workspace_id"]
    with workspace_scope(workspace_id):
        create_follow_up(contact_id=organization, contact_person_id=person, task_type="commitment", task_text="Call Anna")
        assert erase_person(person)
        assert list_follow_ups()[0]["contact_person_id"] is None
        assert erase_organization(organization)
    assert list_follow_ups() == []


def test_clearing_a_person_stage_preserves_a_deal_with_a_review_task(clean_database):
    from gcrm.tools.db_people import save_person
    from gcrm.tools.people_next_step import set_person_next_step

    person = save_person("Anna Example", source="test_fixture", geocode_city=False)
    set_person_next_step(person, "Send details", None)
    deal = get_deals("person", person)[0]
    # A newer active task may be completed, leaving only the original review item.
    task_id = create_follow_up(deal_id=deal["id"], task_type="check_in", task_text="Call")
    task = list_follow_ups()[0]
    change_follow_up_status(task_id, "completed", task["updated_at"])
    with db() as connection:
        assert set_person_stage(connection.cursor(), person, None) == "candidate"
    assert get_deals("person", person)[0]["id"] == deal["id"]


def test_erasing_an_owner_cascades_linked_review_history(clean_database, monkeypatch):
    from gcrm.tools.db_interactions import log_meeting_note

    monkeypatch.setattr("gcrm.tools.db_organizations.geocode", lambda city, country: None)
    organization = save_organization("Example GmbH", "Augsburg", source="test_fixture")
    active = create_follow_up(contact_id=organization, task_type="commitment", task_text="Send details")
    note = log_meeting_note(organization, "phone", "Spoke", follow_up_text="Send details")
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id, updated_at FROM follow_ups WHERE source_kind='interaction' AND source_id=%s", (note,))
        review = cursor.fetchone()
    resolve_review(review["id"], "link", review["updated_at"], linked_task_id=active)
    assert erase_organization(organization)
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT count(*) AS total FROM follow_ups")
        assert cursor.fetchone()["total"] == 0
