"""Bookings on real PostgreSQL: one writer per workspace, holds that expire, retention."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import psycopg2
import pytest

from gcrm.booking.booking_store import (
    NewBooking,
    SlotTaken,
    cancel_booking,
    confirm_hold,
    count_open_holds,
    create_booking,
    decide_request,
    find_person_by_email,
    move_booking,
    purge_old_bookings,
    taken_spans,
)
from gcrm.booking.setup_store import (
    add_booking_block,
    ensure_booking_defaults,
    get_booking_settings,
    list_booking_hours,
    list_booking_types,
    update_booking_settings,
    workspace_for_slug,
)
from gcrm.booking.slots import TimeSpan, occupied_span
from gcrm.db.connection import db
from gcrm.workspace_context import workspace_scope

pytestmark = pytest.mark.integration

START = datetime(2027, 3, 2, 9, tzinfo=timezone.utc)
WEEK = TimeSpan(START - timedelta(days=1), START + timedelta(days=6))


def default_workspace() -> int:
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug='default'")
        return cursor.fetchone()["id"]


@pytest.fixture
def foreign_workspace(clean_database) -> int:
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("INSERT INTO workspaces (name, slug) VALUES ('Other', 'other-booking') "
                       "ON CONFLICT (slug) DO UPDATE SET name=EXCLUDED.name RETURNING id")
        return cursor.fetchone()["id"]


def video_type_id() -> int:
    return next(kind["id"] for kind in list_booking_types() if kind["kind"] == "video")


def new_booking(start=START, status="confirmed", email="erika@example.com") -> NewBooking:
    return NewBooking(booking_type_id=video_type_id(), status=status, starts_at=start,
                      ends_at=start + timedelta(minutes=45),
                      occupied=occupied_span(start, 45, 0, 15), guest_name="Erika Musterfrau", guest_email=email)


@pytest.fixture
def workspace(clean_database):
    workspace_id = default_workspace()
    with workspace_scope(workspace_id):
        ensure_booking_defaults()
        yield workspace_id


def test_defaults_are_created_once(workspace):
    ensure_booking_defaults()
    assert [kind["kind"] for kind in list_booking_types()] == ["call", "video", "visit", "custom"]
    assert len(list_booking_hours()) == 10
    assert get_booking_settings()["is_enabled"] is False


def test_feed_url_is_stored_encrypted_and_read_back(workspace):
    update_booking_settings({"feed_url": "https://calendar.example/api/feed.ics?Key=secret"})
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT feed_url_encrypted FROM booking_settings")
        assert "secret" not in cursor.fetchone()["feed_url_encrypted"]
    assert get_booking_settings()["feed_url"] == "https://calendar.example/api/feed.ics?Key=secret"


def lookup_as_runtime_role(sql: str, params=()):
    """Run one query as the pre-login runtime role, the way the public page runs before a workspace."""
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SET LOCAL ROLE engcrm_app")
        cursor.execute(sql, params)
        return cursor.fetchall()


def test_public_slug_finds_only_an_enabled_page(workspace):
    update_booking_settings({"public_slug": "chris", "feed_url": "https://calendar.example/feed.ics"})
    query = "SELECT workspace_id FROM booking_settings WHERE public_slug=%s AND is_enabled"
    assert lookup_as_runtime_role(query, ("chris",)) == []
    update_booking_settings({"is_enabled": True})
    assert [row["workspace_id"] for row in lookup_as_runtime_role(query, ("chris",))] == [workspace]
    assert workspace_for_slug("chris") == workspace


def test_runtime_role_cannot_read_the_feed_secret(workspace):
    update_booking_settings({"public_slug": "chris", "is_enabled": True, "feed_url": "https://calendar.example/f"})
    with pytest.raises(psycopg2.errors.InsufficientPrivilege):
        lookup_as_runtime_role("SELECT feed_url_encrypted FROM booking_settings")
    with pytest.raises(psycopg2.errors.InsufficientPrivilege):
        lookup_as_runtime_role("SELECT guest_email FROM bookings")


def test_overlapping_booking_is_refused(workspace):
    create_booking(new_booking())
    with pytest.raises(SlotTaken):
        create_booking(new_booking(START + timedelta(minutes=50)))  # inside the 15-minute gap
    create_booking(new_booking(START + timedelta(minutes=60)))


def test_two_people_racing_for_one_slot_get_one_booking(workspace):
    def attempt(email):
        with workspace_scope(workspace):
            try:
                create_booking(new_booking(email=email))
                return "booked"
            except SlotTaken:
                return "taken"

    with ThreadPoolExecutor(max_workers=4) as pool:
        outcomes = list(pool.map(attempt, [f"guest{n}@example.com" for n in range(4)]))
    assert sorted(outcomes) == ["booked", "taken", "taken", "taken"]


def test_expired_hold_frees_the_slot_and_cannot_be_confirmed(workspace):
    held = create_booking(new_booking(status="held"))
    assert count_open_holds("ERIKA@example.com") == 1
    with db() as connection:
        connection.cursor().execute("UPDATE bookings SET hold_expires_at = NOW() - interval '1 minute'")
    assert taken_spans(WEEK, 15) == []
    booking, was_confirmed_now = confirm_hold(held.confirm_token)
    assert was_confirmed_now is False and booking["status"] == "held"
    create_booking(new_booking())


def test_confirm_twice_confirms_once(workspace):
    held = create_booking(new_booking(status="held"))
    first, first_now = confirm_hold(held.confirm_token)
    second, second_now = confirm_hold(held.confirm_token)
    assert (first["status"], first_now) == ("confirmed", True)
    assert (second["status"], second_now) == ("confirmed", False)
    assert confirm_hold("not-a-real-token") == (None, False)


def test_move_raises_sequence_and_ignores_its_own_old_time(workspace):
    created = create_booking(new_booking())
    later = START + timedelta(minutes=30)
    moved = move_booking(created.booking_id, later, later + timedelta(minutes=45), occupied_span(later, 45, 0, 15))
    assert moved["sequence"] == 1 and moved["starts_at"] == later
    other = create_booking(new_booking(START + timedelta(hours=3)))
    with pytest.raises(SlotTaken):
        move_booking(created.booking_id, START + timedelta(hours=3), START + timedelta(hours=3, minutes=45),
                     occupied_span(START + timedelta(hours=3), 45, 0, 15))
    assert other.booking_id != created.booking_id


def test_cancel_twice_cancels_once_and_frees_time(workspace):
    created = create_booking(new_booking())
    cancelled = cancel_booking(created.booking_id)
    assert cancelled["status"] == "cancelled" and cancelled["sequence"] == 1
    assert cancel_booking(created.booking_id) is None
    assert taken_spans(WEEK, 15) == []


def test_request_decided_once(workspace):
    created = create_booking(new_booking(status="requested"))
    assert decide_request(created.booking_id, is_approved=True)["status"] == "confirmed"
    assert decide_request(created.booking_id, is_approved=False) is None


def test_blocks_count_as_taken_with_the_gap(workspace):
    add_booking_block(START, START + timedelta(hours=1), "Dentist")
    assert taken_spans(WEEK, 15) == [TimeSpan(START, START + timedelta(hours=1, minutes=15))]


def test_purge_removes_old_holds_and_old_unlinked_bookings_only(workspace):
    create_booking(new_booking(status="held"))
    old = create_booking(new_booking(START + timedelta(hours=2)))
    kept = create_booking(new_booking(START + timedelta(hours=4)))
    assert purge_old_bookings(datetime.now(timezone.utc)) == 0
    later = START + timedelta(days=200)
    with db() as connection:
        connection.cursor().execute("UPDATE bookings SET created_at = NOW() - interval '2 days'")
        cursor = connection.cursor()
        cursor.execute("INSERT INTO people (name, email) VALUES ('Max Beispiel', 'max@example.com') RETURNING id")
        cursor.execute("UPDATE bookings SET person_id=%s WHERE id=%s", (cursor.fetchone()["id"], kept.booking_id))
    assert purge_old_bookings(later) == 2
    assert purge_old_bookings(later) == 0
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM bookings")
        remaining = {row["id"] for row in cursor.fetchall()}
    assert remaining == {kept.booking_id}
    assert old.booking_id not in remaining


def test_email_match_needs_exactly_one_person(workspace):
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("INSERT INTO people (name, email) VALUES ('Max Beispiel', 'max@example.com') RETURNING id")
        person_id = cursor.fetchone()["id"]
    assert find_person_by_email("MAX@example.com")["id"] == person_id
    assert find_person_by_email("nobody@example.com") is None
    with db() as connection:
        connection.cursor().execute("INSERT INTO people (name, email) VALUES ('Max B.', 'max@example.com')")
    assert find_person_by_email("max@example.com") is None


def test_another_workspace_sees_none_of_it(foreign_workspace, workspace):
    create_booking(new_booking())
    with workspace_scope(foreign_workspace):
        ensure_booking_defaults()
        assert taken_spans(WEEK, 15) == []
        create_booking(new_booking())  # same time, other workspace: no clash
