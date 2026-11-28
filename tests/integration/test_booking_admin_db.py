"""Chris's Bookings page on real PostgreSQL: settings, hours, links, approvals, linking."""
import re
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from gcrm.api import main as app_module
from gcrm.api.auth import require_login
from gcrm.api.main import app
from gcrm.booking import booking_service as service
from gcrm.booking.booking_store import get_booking
from gcrm.booking.setup_store import list_booking_feeds
from gcrm.db.connection import db
from gcrm.workspace_context import workspace_scope

pytestmark = pytest.mark.integration


@pytest.fixture
def outbox(monkeypatch):
    sent = []
    monkeypatch.setattr("gcrm.booking.notifications.send_prepared_email",
                        lambda message, recipient: sent.append((recipient, message)) or True)
    return sent


@pytest.fixture
def signed_in(clean_database, outbox, monkeypatch):
    """A signed-in browser: the session lookup names the workspace, as it does in production."""
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug='default'")
        workspace_id = cursor.fetchone()["id"]

    async def session_identity(request, admin_password):
        return {"workspace_id": workspace_id}

    monkeypatch.setattr(app_module, "refresh_browser_session", session_identity)
    app.dependency_overrides[require_login] = lambda: "admin"
    try:
        yield TestClient(app), workspace_id
    finally:
        app.dependency_overrides.pop(require_login, None)


CALENDAR = "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//x//x//EN\r\nEND:VCALENDAR\r\n"


@pytest.fixture
def calendars_answer(monkeypatch):
    """Every link fetched while adding answers with a calendar, unless a test says otherwise."""
    answers = {}
    monkeypatch.setattr("gcrm.booking.busy_feed.fetch_feed_text", lambda url: answers.get(url, CALENDAR))
    return answers


def post(client, path, data):
    return client.post(path, data=data, follow_redirects=False)


SETTINGS = {"public_slug": "chris", "organizer_email": "termine@example.org", "organizer_name": "Chris Example",
            "host_email": "host@example.net", "min_notice_hours": "24", "horizon_days": "42", "gap_minutes": "15",
            "cancel_cutoff_hours": "12"}


def test_page_shows_defaults_and_the_page_is_off(signed_in):
    client, _ = signed_in
    page = client.get("/bookings/?lang=en")
    assert page.status_code == 200
    assert "The public booking page is off" in page.text
    assert 'value="09:30-12:00, 13:30-16:30"' in page.text


def test_switching_on_needs_sender_and_calendar_address(signed_in):
    client, workspace_id = signed_in
    refused = post(client, "/bookings/settings", {**SETTINGS, "organizer_email": "", "is_enabled": "on"})
    assert "error=" in refused.headers["location"]
    saved = post(client, "/bookings/settings", {**SETTINGS, "is_enabled": "on"})
    assert "msg=saved" in saved.headers["location"]
    with workspace_scope(workspace_id):
        assert service.load_page("chris").settings["is_enabled"] is True


def test_calendar_links_are_added_renamed_and_removed(signed_in, calendars_answer):
    client, workspace_id = signed_in
    business = "https://calendar.example/api/business.ics?Key=business-secret"
    assert "msg=saved" in post(client, "/bookings/feeds", {"label": "Business", "url": business}).headers["location"]
    post(client, "/bookings/feeds", {"label": "Art events", "url": "https://calendar.example/api/art.ics?Key=art"})
    assert "error=" in post(client, "/bookings/feeds", {"label": "Plain", "url": "http://x.example/f"}).headers["location"]
    assert "error=" in post(client, "/bookings/feeds", {"label": " ", "url": business}).headers["location"]
    with workspace_scope(workspace_id):
        feeds = list_booking_feeds()
        assert service.load_page("chris").settings["feed_urls"] == [business, feeds[1]["url"]]
    page = client.get("/bookings/?lang=en").text
    assert "Business" in page and "Art events" in page and "calendar.example" in page
    assert "business-secret" not in page, "the link holds the calendar's key and never goes back to the browser"
    post(client, f"/bookings/feeds/{feeds[0]['id']}/label", {"label": "Engagements"})
    post(client, f"/bookings/feeds/{feeds[1]['id']}/delete", {})
    with workspace_scope(workspace_id):
        assert [(feed["label"], feed["url"]) for feed in list_booking_feeds()] == [("Engagements", business)]
    assert post(client, f"/bookings/feeds/{feeds[1]['id']}/delete", {}).status_code == 404


def test_open_hours_are_saved_as_typed_or_refused(signed_in):
    client, _ = signed_in
    refused = post(client, "/bookings/hours", {"day0": "12:00-09:00"})
    assert "error=" in refused.headers["location"]
    post(client, "/bookings/hours", {"day1": "08:00-10:00"})
    page = client.get("/bookings/?lang=en")
    assert 'name="day1" value="08:00-10:00"' in page.text
    assert 'name="day0" value=""' in page.text


def test_a_type_can_be_switched_off_and_on_again(signed_in):
    client, _ = signed_in
    fields = {f"{kind}_minutes": minutes for kind, minutes in
              (("call", "15"), ("video", "45"), ("visit", "60"), ("custom", "30"))}
    post(client, "/bookings/types", {**fields, "video_active": "on", "visit_active": "on", "custom_active": "on"})
    page = client.get("/bookings/?lang=en")
    assert re.search(r'name="call_active"\s*aria-label', page.text)  # unchecked, still listed
    post(client, "/bookings/types", {**fields, "call_active": "on"})
    assert re.search(r'name="call_active" checked', client.get("/bookings/?lang=en").text)


def test_person_page_button_makes_a_personal_link(signed_in):
    client, _ = signed_in
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("INSERT INTO people (name, email) VALUES ('Max Beispiel', 'max@example.com') RETURNING id")
        person_id = cursor.fetchone()["id"]
    post(client, "/bookings/settings", SETTINGS)
    post(client, "/bookings/links", {"person_id": str(person_id), "label": "Max Beispiel"})
    assert re.search(r"Max Beispiel: <code>[^<]*/book/chris\?link=[A-Za-z0-9_-]{40,}</code>",
                     client.get("/bookings/?lang=en").text)


def _requested_booking(workspace_id: int, client) -> int:
    post(client, "/bookings/settings", {**SETTINGS, "is_enabled": "on"})
    with workspace_scope(workspace_id):
        page = service.load_page("chris")
        now = datetime.now(timezone.utc)
        start = next(iter(service.available_starts(page.types["custom"], page.settings, now, minutes=60)))
        booking = service.book(page, service.BookingForm(
            kind="custom", starts_at=start, guest_name="Erika Musterfrau", guest_email="erika@beispiel.example",
            company="Beispiel GmbH", topic="AI in quality control", custom_minutes=60), link=None, now=now)
    return booking["id"]


def test_approve_a_request_then_link_it_to_a_suggested_person(signed_in, outbox):
    client, workspace_id = signed_in
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("INSERT INTO people (name, email) VALUES ('Erika M.', 'office@beispiel.example') RETURNING id")
        colleague_id = cursor.fetchone()["id"]
    booking_id = _requested_booking(workspace_id, client)
    page = client.get("/bookings/?lang=en")
    assert "Approve" in page.text and f'value="person:{colleague_id}"' in page.text
    post(client, f"/bookings/{booking_id}/action/approve", {})
    post(client, f"/bookings/{booking_id}/link", {"record": f"person:{colleague_id}"})
    with workspace_scope(workspace_id):
        booking = get_booking(booking_id)
    assert booking["status"] == "confirmed" and booking["person_id"] == colleague_id
    assert booking["follow_up_id"] is not None


def test_create_person_from_an_unlinked_booking(signed_in):
    client, workspace_id = signed_in
    booking_id = _requested_booking(workspace_id, client)
    post(client, f"/bookings/{booking_id}/create-person", {})
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id, source FROM people WHERE email='erika@beispiel.example'")
        person = cursor.fetchone()
    assert person["source"] == "manual_web"
    with workspace_scope(workspace_id):
        assert get_booking(booking_id)["person_id"] == person["id"]


def test_unknown_action_is_not_found(signed_in):
    client, workspace_id = signed_in
    booking_id = _requested_booking(workspace_id, client)
    assert post(client, f"/bookings/{booking_id}/action/delete-everything", {}).status_code == 404


def test_block_time_is_added_and_removed(signed_in):
    client, _ = signed_in
    day = (datetime.now(timezone.utc) + timedelta(days=3)).strftime("%d.%m.%Y")
    post(client, "/bookings/blocks", {"day": day, "start": "10:00", "end": "11:30", "note": "Dentist"})
    page = client.get("/bookings/?lang=en").text
    assert "Dentist" in page
    block_id = re.search(r"/bookings/blocks/(\d+)/delete", page).group(1)
    post(client, f"/bookings/blocks/{block_id}/delete", {})
    assert "Dentist" not in client.get("/bookings/?lang=en").text


def test_page_renders_on_a_fresh_database_without_a_workspace_in_the_session(clean_database):
    """The every-page crawl signs in without a session workspace; the page must set itself up, not 500."""
    app.dependency_overrides[require_login] = lambda: "admin"
    try:
        page = TestClient(app, raise_server_exceptions=False).get("/bookings/?lang=en")
    finally:
        app.dependency_overrides.pop(require_login, None)
    assert page.status_code == 200
    assert "The public booking page is off" in page.text
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT s.workspace_id, w.slug FROM booking_settings s JOIN workspaces w ON w.id = s.workspace_id")
        assert [row["slug"] for row in cursor.fetchall()] == ["default"]


def test_owner_previews_the_guest_page_while_the_public_page_is_off(signed_in):
    client, _ = signed_in
    post(client, "/bookings/settings", SETTINGS)
    assert client.get("/book/chris").status_code == 404
    assert 'href="/bookings/preview"' in client.get("/bookings/?lang=en").text
    start = client.get("/bookings/preview?lang=en")
    assert start.status_code == 200
    assert "Preview: this is the page your guests see" in start.text
    assert 'href="/bookings/preview/video?lang=en"' in start.text and 'href="/book/' not in start.text
    times = client.get("/bookings/preview/video?lang=en")
    assert times.status_code == 200
    assert 'name="start"' in times.text, "the preview shows the real free times"
    assert '<button type="submit" disabled>' in times.text
    assert client.post("/bookings/preview/video", data={}).status_code == 405


def test_preview_of_a_switched_off_type_is_not_found(signed_in):
    client, _ = signed_in
    post(client, "/bookings/types", {"call_minutes": "15", "call_travel": "0", "video_minutes": "45",
                                     "video_travel": "0", "visit_minutes": "60", "visit_travel": "60",
                                     "custom_minutes": "30", "custom_travel": "0", "video_active": "on"})
    assert client.get("/bookings/preview/call").status_code == 404
    assert client.get("/bookings/preview/video").status_code == 200


def test_each_types_weekdays_sit_together_in_one_row(signed_in):
    client, _ = signed_in
    page = client.get("/bookings/?lang=en").text
    rows = re.findall(r'<div class="days">(.*?)</div>', page, re.S)
    assert len(rows) == 4
    assert all(row.count('type="checkbox"') == 7 for row in rows)


def test_a_link_that_no_longer_decrypts_shows_up_for_removal_and_closes_the_page(signed_in):
    client, workspace_id = signed_in
    post(client, "/bookings/settings", SETTINGS)
    with workspace_scope(workspace_id), db() as connection:
        connection.cursor().execute("INSERT INTO booking_feeds (label, url_encrypted) VALUES ('Old key', 'not-a-token')")
    page = client.get("/bookings/?lang=en")
    assert page.status_code == 200 and "Old key" in page.text and "cannot be read" in page.text
    times = client.get("/bookings/preview/video?lang=en")
    assert times.status_code == 200 and 'name="start"' not in times.text, "an unreadable calendar offers no times"
    with workspace_scope(workspace_id):
        feed_id = list_booking_feeds()[0]["id"]
    post(client, f"/bookings/feeds/{feed_id}/delete", {})
    assert 'name="start"' in client.get("/bookings/preview/video?lang=en").text


def test_a_link_that_is_not_a_calendar_is_refused_when_added(signed_in, calendars_answer):
    client, workspace_id = signed_in
    calendars_answer["https://calendar.proton.me/u/1/"] = "<!doctype html><html><body>Proton Calendar</body></html>"
    refused = post(client, "/bookings/feeds", {"label": "Proton", "url": "https://calendar.proton.me/u/1/"})
    assert "error=feed_not_calendar" in refused.headers["location"]
    with workspace_scope(workspace_id):
        assert list_booking_feeds() == []
    page = client.get(refused.headers["location"] + "&lang=en")
    assert "limited view" in page.text.lower()
