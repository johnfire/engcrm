"""The field tools (gcrm/mcp/field.py) against the real schema: what Claude saves for
Chris on the road, and that undo takes each kind of change back. Google Places and
OpenStreetMap are replaced; everything else is the real database."""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from gcrm.db.connection import db
from gcrm.mcp import field
from gcrm.mcp.field import FieldError, FieldUser
from gcrm.tools.deal_records import get_deals, set_deal_next_step
from gcrm.tools.field_locations import record_points
from gcrm.tools.follow_ups import (
    create_follow_up,
    list_follow_ups,
    resolve_review,
    update_follow_up,
)
from gcrm.workspace_context import set_workspace_id

pytestmark = pytest.mark.integration

PLACES = [
    {"name": "Bäckerei Maier", "place_id": "ChIJbakery", "address": "Hauptplatz 12, 86899 Landsberg am Lech",
     "city": "Landsberg am Lech", "country": "DE", "type": "Bäckerei", "latitude": 48.04785,
     "longitude": 10.8769, "distance_m": 9},
    {"name": "Optik Huber", "place_id": "ChIJoptician", "address": "Hauptplatz 14", "city": "Landsberg am Lech",
     "country": "DE", "type": "Optiker", "latitude": 48.048, "longitude": 10.8772, "distance_m": 37},
]


@pytest.fixture
def chris(clean_database):
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug = 'default'")
        workspace_id = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO users (email, password_hash, role, workspace_id) "
                       "VALUES ('chris@example.test', 'hash', 'admin', %s) RETURNING id", (workspace_id,))
        user = FieldUser(cursor.fetchone()["id"], workspace_id)
    set_workspace_id(workspace_id)  # as the remote MCP does for each call
    yield user
    set_workspace_id(None)


def _stand_here(user: FieldUser, minutes_ago: int = 1) -> None:
    record_points(user.user_id, [{"latitude": 48.0478, "longitude": 10.8768, "accuracy_m": 8.0,
                                  "recorded_at": datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)}])


def _live(table: str, row_id: int) -> bool:
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute(f"SELECT deleted_at IS NULL AS live FROM {table} WHERE id = %s", (row_id,))
        return cursor.fetchone()["live"]


def test_without_a_fresh_position_claude_asks_for_the_address(chris):
    with pytest.raises(FieldError, match="Field mode"):
        field.where_am_i(chris)
    _stand_here(chris, minutes_ago=30)
    with pytest.raises(FieldError, match="30 minutes old"):
        field.businesses_here(chris)


def test_undo_restores_the_task_actually_completed_not_its_next_sibling(chris):
    organization = field.add_organization(chris, "Example GmbH", city="Augsburg")["organization_id"]
    deal = get_deals("organization", organization, chris.workspace_id)[0]
    first = create_follow_up(deal_id=deal["id"], task_type="commitment", task_text="Send proposal",
                             due_date=datetime(2026, 12, 1).date(), workspace_id=chris.workspace_id)
    second = create_follow_up(deal_id=deal["id"], task_type="check_in", task_text="Call",
                              due_date=datetime(2026, 12, 2).date(), workspace_id=chris.workspace_id)
    field.set_next_step(chris, "", organization_id=organization)
    assert [task["id"] for task in list_follow_ups(chris.workspace_id)] == [second]
    field.undo_last(chris)
    assert [(task["id"], task["task_text"]) for task in list_follow_ups(chris.workspace_id)] == [
        (first, "Send proposal"), (second, "Call")]


def test_undo_activity_dismisses_its_promise_without_reviving_it(chris):
    organization = field.add_organization(chris, "Example GmbH", city="Augsburg")["organization_id"]
    activity = field.log_activity(chris, "Spoke to the owner", organization_id=organization,
                                  follow_up_date="17.11.2026")
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id, status FROM follow_ups WHERE source_kind='interaction' AND source_id=%s",
                       (activity["activity_id"],))
        task = cursor.fetchone()
        assert task["status"] == "review"
    field.undo_last(chris)
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT status FROM follow_ups WHERE id=%s", (task["id"],))
        assert cursor.fetchone()["status"] == "dismissed"


def test_undo_activity_refuses_to_discard_a_changed_promise(chris):
    organization = field.add_organization(chris, "Example GmbH", city="Augsburg")["organization_id"]
    activity = field.log_activity(chris, "Spoke to the owner", organization_id=organization,
                                  follow_up_date="17.11.2026")
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id, updated_at FROM follow_ups WHERE source_kind='interaction' AND source_id=%s",
                       (activity["activity_id"],))
        task = cursor.fetchone()
    resolve_review(task["id"], "keep", task["updated_at"], task_type="commitment", task_text="Send quote",
                   workspace_id=chris.workspace_id)
    with pytest.raises(FieldError, match="changed"):
        field.undo_last(chris)
    assert _live("interactions", activity["activity_id"])
    assert [task["id"] for task in list_follow_ups(chris.workspace_id)] == [task["id"]]


def test_the_whole_first_visit_and_undo_of_each_step(chris):
    _stand_here(chris)
    with patch("gcrm.mcp.field.places_nearby", return_value=[dict(p) for p in PLACES]) as nearby:
        here = field.businesses_here(chris)
    assert nearby.call_args.args == (48.0478, 10.8768)
    assert [b["name"] for b in here["businesses"]] == ["Bäckerei Maier", "Optik Huber"]
    assert all(b["in_engcrm"] is None for b in here["businesses"])

    bakery = PLACES[0]
    saved = field.add_organization(chris, bakery["name"], city=bakery["city"], address=bakery["address"],
                                   type=bakery["type"], place_id=bakery["place_id"],
                                   latitude=bakery["latitude"], longitude=bakery["longitude"])
    org = saved["organization_id"]
    assert saved["said"] == f"Saved Bäckerei Maier, Hauptplatz 12, 86899 Landsberg am Lech (#{org})."
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT source, address, latitude, google_data->>'id' AS place_id, workspace_id "
                       "FROM contacts WHERE id = %s", (org,))
        assert dict(cursor.fetchone()) == {"source": "claude_field", "address": bakery["address"],
                                           "latitude": 48.04785, "place_id": "ChIJbakery",
                                           "workspace_id": chris.workspace_id}

    # Asked again, the bakery is now known, and saving it twice saves nothing.
    with patch("gcrm.mcp.field.places_nearby", return_value=[dict(p) for p in PLACES]):
        again = field.businesses_here(chris)
    assert again["businesses"][0]["in_engcrm"] == {"organization_id": org, "name": "Bäckerei Maier"}
    assert field.add_organization(chris, "Bäckerei Maier", city="Landsberg am Lech")["saved"] is False

    maria = field.add_person(chris, org, "Maria Maier", title="Inhaberin")["person_id"]
    visit = field.log_activity(chris, "Owner was friendly, wants prices.", organization_id=org, kind="drop_in",
                               minutes=10, attitude=["warm"], my_read=["trustworthy"], materials_left="Flyer",
                               follow_up_promised="send price list", follow_up_date="17.11.2026",
                               follow_up_type="commitment", offer="general")
    assert visit["said"] == "Logged a drop-in at Bäckerei Maier; follow-up send price list on 17.11.2026."
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT method, duration_minutes, attitude, my_read, materials_left, next_action, "
                       "next_action_date::text FROM interactions WHERE id = %s", (visit["activity_id"],))
        assert dict(cursor.fetchone()) == {"method": "in_person", "duration_minutes": 10, "attitude": ["warm"],
                                           "my_read": ["trustworthy"], "materials_left": "Flyer",
                                           "next_action": "send price list", "next_action_date": "2026-11-17"}
    talk = field.log_activity(chris, "Talked about AI for the shop.", person_id=maria, kind="meeting")
    field.set_ratings(chris, organization_id=org, priority=2, short_term_value=3)
    field.set_ratings(chris, person_id=maria, priority=1)
    step = field.set_next_step(chris, "Send the price list", due="17.11.2026", organization_id=org,
                               follow_up_type="commitment")
    assert step["said"] == "Next step on Consulting: Send the price list, by 17.11.2026."

    # Undo walks back newest first: next step, both ratings, both activities, person, organization.
    assert field.undo_last(chris)["said"].startswith("Undone: Next step")
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT next_step FROM deals WHERE contact_id = %s AND deleted_at IS NULL", (org,))
        assert cursor.fetchone()["next_step"] is None
    field.undo_last(chris)  # person rating
    field.undo_last(chris)  # organization ratings
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT priority, short_term_value FROM contact_user_priorities WHERE contact_id = %s", (org,))
        assert dict(cursor.fetchone() or {"priority": None, "short_term_value": None}) == {
            "priority": None, "short_term_value": None}
    field.undo_last(chris)
    assert not _live("people_interactions", talk["activity_id"])
    field.undo_last(chris)
    assert not _live("interactions", visit["activity_id"])
    field.undo_last(chris)
    assert not _live("people", maria)
    field.undo_last(chris)
    assert not _live("contacts", org)
    with pytest.raises(FieldError, match="nothing of mine left"):
        field.undo_last(chris)


def test_refusals_are_said_back_not_crashes(chris):
    org = field.add_organization(chris, "Optik Huber", city="Landsberg am Lech")["organization_id"]
    with pytest.raises(FieldError, match="one organization or one person"):
        field.log_activity(chris, "x")
    with pytest.raises(FieldError, match="kind is one of"):
        field.log_activity(chris, "x", organization_id=org, kind="telepathy")
    with pytest.raises(FieldError, match="Attitudes"):
        field.log_activity(chris, "x", organization_id=org, attitude=["ecstatic"])
    with pytest.raises(FieldError, match="no organization #999999"):
        field.add_person(chris, 999999, "Nobody")
    with pytest.raises(FieldError, match="1 to 5"):
        person = field.add_person(chris, org, "Hans Huber")["person_id"]
        field.set_ratings(chris, person_id=person, priority=6)


def test_another_workspace_is_out_of_reach(chris):
    # Seed the other tenant as the operator, then restore the connector scope.
    set_workspace_id(None)
    with db() as connection:
        cursor = connection.cursor()
        # Workspaces survive clean_database, so a rerun finds this one already there.
        cursor.execute("INSERT INTO workspaces (name, slug) VALUES ('Elsewhere', 'elsewhere') "
                       "ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name RETURNING id")
        other = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO contacts (name, city, workspace_id) VALUES ('Foreign Co', 'Ulm', %s) "
                       "RETURNING id", (other,))
        foreign = cursor.fetchone()["id"]
    set_workspace_id(chris.workspace_id)
    assert field.find_organization(chris, "Foreign") == []
    with pytest.raises(FieldError, match=f"no organization #{foreign}"):
        field.log_activity(chris, "x", organization_id=foreign)


# --- follow-up types ----------------------------------------------------------------
# A follow-up without a type is stored for review and never shows on the Follow-ups list,
# so the connector (which has no old clients) asks for the type instead of saving it.

def _rows(sql: str, *values) -> list[dict]:
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute(sql, values)
        return [dict(row) for row in cursor.fetchall()]


def _tasks() -> list[tuple[str, str, str | None]]:
    return [(r["task_text"], r["status"], r["task_type"])
            for r in _rows("SELECT task_text, status, task_type FROM follow_ups ORDER BY id")]


def _deal(user: FieldUser) -> tuple[int, dict]:
    organization = field.add_organization(user, "Example GmbH", city="Augsburg")["organization_id"]
    return organization, get_deals("organization", organization, user.workspace_id)[0]


@pytest.mark.parametrize("follow_up_type", ["", "  ", "someday"])
def test_a_next_step_without_a_valid_type_is_not_saved_and_claude_is_told_to_ask(chris, follow_up_type):
    organization, deal = _deal(chris)
    with pytest.raises(FieldError, match="Ask Chris.*commitment.*check_in"):
        field.set_next_step(chris, "Meet in Augsburg", organization_id=organization, follow_up_type=follow_up_type)
    assert _tasks() == []
    assert get_deals("organization", organization, chris.workspace_id)[0]["next_step"] is None
    assert _rows("SELECT 1 FROM mcp_actions WHERE kind = 'next_step'") == []


def test_a_typed_next_step_goes_straight_to_the_follow_ups_list_and_undo_takes_it_off(chris):
    organization, _ = _deal(chris)
    field.set_next_step(chris, "Meet in Augsburg", due="4.12.2026", organization_id=organization,
                        follow_up_type="check_in")
    assert _tasks() == [("Meet in Augsburg", "active", "check_in")]
    field.undo_last(chris)
    assert list_follow_ups(chris.workspace_id) == []
    assert get_deals("organization", organization, chris.workspace_id)[0]["next_step"] is None


def test_clearing_a_next_step_needs_no_type(chris):
    organization, _ = _deal(chris)
    field.set_next_step(chris, "Send the quote", organization_id=organization, follow_up_type="commitment")
    assert field.set_next_step(chris, "  ", organization_id=organization)["said"] == (
        "Next step on Consulting: cleared.")
    assert _tasks() == [("Send the quote", "completed", "commitment")]


def test_undo_puts_a_step_that_waited_for_review_back_without_a_type(chris):
    organization, deal = _deal(chris)
    set_deal_next_step(deal["id"], "Meet in Augsburg", None, chris.workspace_id)   # an old phone build's step
    field.set_next_step(chris, "Meet in Augsburg", organization_id=organization, follow_up_type="check_in")
    assert _tasks() == [("Meet in Augsburg", "active", "check_in")]
    field.undo_last(chris)
    assert _tasks() == [("Meet in Augsburg", "review", None)]


def test_undo_restores_the_type_a_next_step_had_before(chris):
    organization, deal = _deal(chris)
    create_follow_up(deal_id=deal["id"], task_type="commitment", task_text="Send the quote",
                     workspace_id=chris.workspace_id)
    field.set_next_step(chris, "Ask how the quote landed", organization_id=organization, follow_up_type="check_in")
    field.undo_last(chris)
    assert _tasks() == [("Send the quote", "active", "commitment")]


@pytest.mark.parametrize("follow_up_type", ["", "someday"])
def test_a_promise_without_a_valid_type_logs_nothing(chris, follow_up_type):
    organization, _ = _deal(chris)
    with pytest.raises(FieldError, match="Ask Chris.*commitment.*check_in"):
        field.log_activity(chris, "Spoke to the owner", organization_id=organization,
                           follow_up_promised="Send quote", follow_up_type=follow_up_type)
    assert _rows("SELECT 1 FROM interactions") == [] and _tasks() == []
    assert _rows("SELECT 1 FROM mcp_actions WHERE kind = 'organization_activity'") == []


def test_a_typed_promise_is_active_and_undo_dismisses_it(chris):
    organization, _ = _deal(chris)
    field.log_activity(chris, "Spoke to the owner", organization_id=organization,
                       follow_up_promised="Send quote", follow_up_type="commitment")
    assert [task["task_text"] for task in list_follow_ups(chris.workspace_id)] == ["Send quote"]
    field.undo_last(chris)
    assert _tasks() == [("Send quote", "dismissed", "commitment")]


def test_undo_refuses_to_discard_a_typed_promise_changed_since(chris):
    organization, _ = _deal(chris)
    activity = field.log_activity(chris, "Spoke to the owner", organization_id=organization,
                                  follow_up_promised="Send quote", follow_up_type="commitment")
    (task,) = list_follow_ups(chris.workspace_id)
    update_follow_up(task["id"], task_type="commitment", task_text="Send the revised quote", due_date=None,
                     version=task["updated_at"], workspace_id=chris.workspace_id)
    with pytest.raises(FieldError, match="changed"):
        field.undo_last(chris)
    assert _live("interactions", activity["activity_id"])


def test_an_activity_with_only_a_follow_up_date_needs_no_type(chris):
    organization, _ = _deal(chris)
    field.log_activity(chris, "Spoke to the owner", organization_id=organization, follow_up_date="4.12.2026")
    assert _tasks() == [("", "review", None)]


def test_a_typed_promise_on_the_deals_offer_is_active_but_not_yet_the_deals_next_step(chris):
    """Pins what happens today, including the doubtful part: logging an activity writes the follow-up row
    but does not refresh the deal's next step, so the deal card shows nothing while the promise is on the
    Follow-ups list, and a next step saved afterwards edits that promise instead of adding a second task."""
    organization, deal = _deal(chris)
    field.log_activity(chris, "Spoke to the owner", organization_id=organization, offer=deal["offer_slug"],
                       follow_up_promised="Send quote", follow_up_type="commitment")
    (promise,) = list_follow_ups(chris.workspace_id)
    assert (promise["deal_id"], promise["task_text"], promise["task_type"]) == (deal["id"], "Send quote",
                                                                                "commitment")
    assert get_deals("organization", organization, chris.workspace_id)[0]["next_step"] is None

    field.set_next_step(chris, "Call next week", organization_id=organization, follow_up_type="check_in")
    assert [(t["id"], t["task_text"], t["task_type"]) for t in list_follow_ups(chris.workspace_id)] == [
        (promise["id"], "Call next week", "check_in")]

    field.undo_last(chris)     # the promise comes back, and only now does the deal show it
    assert _tasks() == [("Send quote", "active", "commitment")]
    assert get_deals("organization", organization, chris.workspace_id)[0]["next_step"] == "Send quote"
