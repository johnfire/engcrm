"""The field tools (gcrm/mcp/field.py) against the real schema: what Claude saves for
Chris on the road, and that undo takes each kind of change back. Google Places and
OpenStreetMap are replaced; everything else is the real database."""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from gcrm.db.connection import db
from gcrm.mcp import field
from gcrm.mcp.field import FieldError, FieldUser
from gcrm.tools.field_locations import record_points
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
                               follow_up_promised="send price list", follow_up_date="17.11.2026")
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
    step = field.set_next_step(chris, "Send the price list", due="17.11.2026", organization_id=org)
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
