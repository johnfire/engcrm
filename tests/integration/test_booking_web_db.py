"""Public booking pages end to end on real PostgreSQL: book, confirm, manage, cancel."""
import html
import re

import pytest
from fastapi.testclient import TestClient

from gcrm.api.main import app
from gcrm.api.routers import booking_public
from gcrm.booking.setup_store import ensure_booking_defaults, update_booking_settings
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
def client(clean_database, outbox):
    for limiter in (booking_public._page_limiter, booking_public._write_limiter, booking_public._email_limiter):
        limiter.reset()
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug='default'")
        workspace_id = cursor.fetchone()["id"]
    with workspace_scope(workspace_id):
        ensure_booking_defaults()
        update_booking_settings({"public_slug": "chris", "organizer_email": "termine@example.org",
                                 "organizer_name": "Chris Example", "host_email": "host@example.net"})
    return TestClient(app), workspace_id


def enable(workspace_id: int) -> None:
    with workspace_scope(workspace_id):
        update_booking_settings({"is_enabled": True})


def first_start(page_html: str) -> str:
    return html.unescape(re.search(r'name="start" value="([^"]+)"', page_html).group(1))


def book_video(test_client, **fields):
    page = test_client.get("/book/chris/video?lang=de")
    data = {"start": first_start(page.text), "guest_name": "Erika Musterfrau", "guest_email": "erika@example.com"}
    data.update(fields)
    return test_client.post("/book/chris/video?lang=de", data=data)


def link_from(outbox, path: str) -> str:
    message = next(sent for recipient, sent in reversed(outbox) if recipient == "erika@example.com")
    plain = next(part for part in message.walk() if part.get_content_type() == "text/plain")
    body = plain.get_payload(decode=True).decode()
    return re.search(rf"(/book/chris/{path}/[A-Za-z0-9_-]+)", body).group(1)


def booking_status() -> str:
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT status FROM bookings")
        return cursor.fetchone()["status"]


def test_a_disabled_page_does_not_exist(client):
    test_client, _ = client
    assert test_client.get("/book/chris").status_code == 404


def test_start_page_offers_the_four_types(client):
    test_client, workspace_id = client
    enable(workspace_id)
    page = test_client.get("/book/chris?lang=en")
    assert page.status_code == 200
    for kind in ("call", "video", "visit", "custom"):
        assert f"/book/chris/{kind}" in page.text
    assert "Video meeting (45 min)" in page.text


def test_book_then_confirm_with_a_button_not_with_the_link(client, outbox):
    test_client, workspace_id = client
    enable(workspace_id)
    done = book_video(test_client)
    assert done.status_code == 200 and "Fast geschafft" in done.text
    confirm_path = link_from(outbox, "confirm")
    looked_at = test_client.get(confirm_path)  # what a mail scanner does
    assert looked_at.status_code == 200 and booking_status() == "held"
    confirmed = test_client.post(confirm_path)
    assert "Ihr Termin steht" in confirmed.text and booking_status() == "confirmed"
    assert sorted(recipient for recipient, _ in outbox[1:]) == ["erika@example.com", "host@example.net"]


def test_manage_link_downloads_the_invite_and_cancels(client, outbox):
    test_client, workspace_id = client
    enable(workspace_id)
    book_video(test_client)
    test_client.post(link_from(outbox, "confirm"))
    manage_path = link_from(outbox, "manage")
    manage = test_client.get(manage_path)
    assert manage.status_code == 200 and "bestätigt" in manage.text
    invite = test_client.get(manage_path + "/invite.ics")
    assert invite.headers["content-type"].startswith("text/calendar") and b"METHOD:REQUEST" in invite.content
    cancelled = test_client.post(manage_path + "/cancel")
    assert "abgesagt" in cancelled.text and booking_status() == "cancelled"


def test_a_made_up_start_time_is_refused(client):
    test_client, workspace_id = client
    enable(workspace_id)
    refused = book_video(test_client, start="2030-01-01T03:07:00+00:00")
    assert refused.status_code == 409 and "vergeben" in refused.text


def test_the_honeypot_books_nothing(client, outbox):
    test_client, workspace_id = client
    enable(workspace_id)
    trapped = book_video(test_client, website="https://spam.example")
    assert trapped.status_code == 200 and outbox == []
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT count(*) AS bookings FROM bookings")
        assert cursor.fetchone()["bookings"] == 0


def test_an_unknown_manage_token_is_not_found(client):
    test_client, workspace_id = client
    enable(workspace_id)
    assert test_client.get("/book/chris/manage/not-a-token").status_code == 404
