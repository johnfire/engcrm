"""The follow-up type through offline sync. A next step or promise that carries a type goes
straight to the Follow-ups list; one without (an older app, an edit queued before the update)
is still saved, for review, and never refused."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from gcrm.audit_context import audit_scope
from gcrm.db.connection import db
from gcrm.sync.contracts import SyncCreate, SyncUpdate
from gcrm.tools.db_sync_create import apply_sync_create
from gcrm.tools.db_sync_push import apply_sync_update
from gcrm.tools.db_sync_review import restore_provisional_change
from gcrm.workspace_context import workspace_scope

pytestmark = pytest.mark.integration

STEP = {"next_step": "Send proposal", "next_step_date": "2026-12-04"}


@pytest.fixture
def phone(clean_database):
    """A registered phone, and one organization with a Consulting deal."""
    device = uuid4()
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug='default'")
        workspace = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO users(email,password_hash,workspace_id,role) VALUES "
                       "('phone-types@example.test','hash',%s,'admin') RETURNING id", (workspace,))
        user = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO mobile_sync_devices(workspace_id,user_id,device_id,server_environment,app_version,"
                       "schema_version) VALUES (%s,%s,%s,'production','1',1)", (workspace, user, str(device)))
        cursor.execute("INSERT INTO contacts(name) VALUES ('Beispiel Werke GmbH') RETURNING id,sync_id")
        organization = cursor.fetchone()
        cursor.execute("INSERT INTO deals(workspace_id,offer_id,contact_id) "
                       "VALUES (%s,offer_id_for(%s,'consulting'),%s) RETURNING id,sync_id",
                       (workspace, workspace, organization["id"]))
        deal = cursor.fetchone()
    return {"workspace": workspace, "user": user, "device": device, "deal": deal, "organization": organization}


def _push(phone, patch: dict, minutes: int = 1) -> dict:
    """One offline edit of the deal, saved on the phone `minutes` from now."""
    update = SyncUpdate(mutation_id=uuid4(), device_id=phone["device"], entity_kind="deal",
                        entity_sync_id=phone["deal"]["sync_id"], operation="update",
                        changed_at=datetime.now(UTC) + timedelta(minutes=minutes), patch=patch)
    with workspace_scope(phone["workspace"]), audit_scope(f"user:{phone['user']}", "user", "push-type"):
        return apply_sync_update(phone["workspace"], phone["user"], "production", update)


def _rows(sql: str, *values) -> list[dict]:
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute(sql, values)
        return [dict(row) for row in cursor.fetchall()]


def _tasks() -> list[tuple[str, str, str | None]]:
    return [(r["task_text"], r["status"], r["task_type"])
            for r in _rows("SELECT task_text, status, task_type FROM follow_ups ORDER BY id")]


def test_a_typed_offline_next_step_lands_on_the_active_list(phone):
    result = _push(phone, {**STEP, "task_type": "check_in"})
    assert result["status"] == "applied" and result["ignored_fields"] == []
    assert result["winning_fields"] == ["next_step", "next_step_date"]    # the type is no field of its own
    assert _tasks() == [("Send proposal", "active", "check_in")]


@pytest.mark.parametrize("untyped", [{}, {"task_type": None}])
def test_an_offline_next_step_without_a_type_is_still_saved_for_review(phone, untyped):
    assert _push(phone, {**STEP, **untyped})["status"] == "applied"
    assert _tasks() == [("Send proposal", "review", None)]


def test_the_same_step_saved_again_with_a_type_leaves_review_without_a_copy(phone):
    _push(phone, STEP, minutes=1)
    assert _push(phone, {**STEP, "task_type": "commitment"}, minutes=2)["status"] == "applied"
    assert _tasks() == [("Send proposal", "active", "commitment")]
    logged = len(_rows("SELECT 1 FROM interactions"))
    assert _push(phone, {**STEP, "task_type": "commitment"}, minutes=3)["status"] == "applied"
    assert _tasks() == [("Send proposal", "active", "commitment")]
    assert len(_rows("SELECT 1 FROM interactions")) == logged            # nothing changed, nothing logged


def test_a_typed_offline_clear_completes_the_step(phone):
    _push(phone, {**STEP, "task_type": "check_in"}, minutes=1)
    assert _push(phone, {"next_step": None, "next_step_date": None}, minutes=2)["status"] == "applied"
    assert _tasks() == [("Send proposal", "completed", "check_in")]


def test_an_older_edit_cannot_change_the_type_of_a_newer_step(phone):
    _push(phone, {**STEP, "task_type": "check_in"}, minutes=3)
    older = _push(phone, {"next_step": "Old words", "next_step_date": "2026-12-01", "task_type": "commitment"},
                  minutes=1)
    assert older["status"] == "ignored_older"
    assert _tasks() == [("Send proposal", "active", "check_in")]


def test_a_type_whose_words_lost_is_not_given_to_the_newer_words(phone):
    _push(phone, {"next_step": "Newer words"}, minutes=5)
    result = _push(phone, {"next_step": "Older words", "next_step_date": "2026-12-04", "task_type": "check_in"},
                   minutes=3)
    assert result["status"] == "partially_applied" and result["ignored_fields"] == ["next_step"]
    assert _tasks() == [("Newer words", "review", None)]


@pytest.mark.parametrize("patch", [{**STEP, "task_type": "someday"}, {"task_type": "check_in"}])
def test_an_unknown_type_or_a_type_alone_is_not_applied(phone, patch):
    assert _push(phone, patch)["status"] == "rejected_validation"
    assert _tasks() == []


def test_a_typed_step_for_a_removed_deal_keeps_its_type_through_review(phone):
    with db() as connection:
        connection.cursor().execute("UPDATE deals SET deleted_at=now() WHERE id=%s", (phone["deal"]["id"],))
    assert _push(phone, {**STEP, "task_type": "commitment"})["status"] == "provisional"
    (proposal,) = _rows("SELECT id, patch FROM provisional_mobile_changes")
    assert proposal["patch"]["task_type"] == "commitment"
    with workspace_scope(phone["workspace"]), audit_scope(f"user:{phone['user']}", "user", "review-type"):
        assert restore_provisional_change(phone["workspace"], phone["user"], proposal["id"]) is True
    assert _tasks() == [("Send proposal", "active", "commitment")]


@pytest.mark.parametrize("sent, expected", [({}, ("review", None)),
                                            ({"follow_up_type": None}, ("review", None)),
                                            ({"follow_up_type": "check_in"}, ("active", "check_in"))])
def test_an_offline_activity_promise_is_saved_with_or_without_a_type(phone, sent, expected):
    creation = SyncCreate(mutation_id=uuid4(), device_id=phone["device"], entity_kind="organization_activity",
                          entity_sync_id=uuid4(), operation="create", changed_at=datetime.now(UTC),
                          patch={"organization_sync_id": str(phone["organization"]["sync_id"]), "summary": "Spoke",
                                 "next_action": "Send quote", **sent})
    with workspace_scope(phone["workspace"]), audit_scope(f"user:{phone['user']}", "user", "create-type"):
        assert apply_sync_create(phone["workspace"], phone["user"], "production", creation)["status"] == "applied"
    assert _tasks() == [("Send quote", *expected)]
