"""The Settings → Backups screen: schedule it, send one now, download one, on the real schema."""
import io
import zipfile
from datetime import datetime, time, timezone

import pytest
from fastapi.testclient import TestClient

import gcrm.api.main as main
from gcrm.api.auth import require_admin, require_login
from gcrm.api.routers import backups
from gcrm.db.connection import db
from gcrm.tools.backup_schedule import (
    deliver_backup,
    get_schedule,
    list_backup_files,
    save_schedule,
)
from gcrm.tools.db_organizations import save_organization
from gcrm.workspace_context import workspace_scope

pytestmark = pytest.mark.integration


def _user(workspace: int, email: str, role: str = "admin") -> int:
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("INSERT INTO users (email, name, password_hash, role, workspace_id, is_active, ui_language) "
                       "VALUES (%s, %s, 'x', %s, %s, TRUE, 'en') RETURNING id", (email, email.split("@")[0], role, workspace))
        return cursor.fetchone()["id"]


@pytest.fixture
def world(clean_database, monkeypatch):
    monkeypatch.setattr("gcrm.tools.db_organizations.geocode", lambda city, country: None)
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug = 'default'")
        first = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO workspaces (slug, name) VALUES ('other-customer', 'Other') "
                       "ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name RETURNING id")
        second = cursor.fetchone()["id"]
    admins = {first: _user(first, "owner@first.example"), second: _user(second, "owner@second.example")}
    with workspace_scope(first):
        save_organization("Brandt Maschinenbau", "Augsburg", source="test_fixture")
    with workspace_scope(second):
        save_organization("Kessler Logistik", "Ulm", source="test_fixture")
    return {"first": first, "second": second, "admins": admins}


@pytest.fixture
def web(world, monkeypatch):
    """A browser signed in as the first workspace's admin."""
    sent = []
    monkeypatch.setattr(backups, "send_backup_mail",
                        lambda to, subject, body, attachment=None: sent.append((to, attachment)) or True)
    state = {"workspace": world["first"], "user": world["admins"][world["first"]]}
    monkeypatch.setattr(backups, "_workspace_id", lambda request: state["workspace"])
    monkeypatch.setattr(backups, "_user_id", lambda request: state["user"])
    main.app.dependency_overrides[require_login] = lambda: "admin"
    main.app.dependency_overrides[require_admin] = lambda: "admin"
    client = TestClient(main.app)
    client.sent, client.state = sent, state
    yield client
    main.app.dependency_overrides.pop(require_login, None)
    main.app.dependency_overrides.pop(require_admin, None)


def _post(web, path, **data):
    return web.post(path, data=data, follow_redirects=False)


def test_an_admin_schedules_backups_and_sees_the_schedule(web, world):
    response = _post(web, "/settings/backup", frequency="weekly", weekday="2", at_time="06:30",
                     timezone="Europe/Berlin", recipient_user_id=str(world["admins"][world["first"]]))
    assert response.status_code == 303 and response.headers["location"].startswith("/settings")
    with workspace_scope(world["first"]):
        saved = get_schedule()
    assert (saved["frequency"], saved["weekday"], saved["at_time"]) == ("weekly", 2, time(6, 30))
    assert saved["next_run_at"] > datetime.now(timezone.utc)


def test_another_workspaces_admin_cannot_be_the_recipient(web, world):
    stranger = world["admins"][world["second"]]
    response = _post(web, "/settings/backup", frequency="daily", weekday="0", at_time="03:00",
                     timezone="Europe/Berlin", recipient_user_id=str(stranger))
    assert response.status_code == 400
    with workspace_scope(world["first"]):
        assert get_schedule()["frequency"] == "off"


@pytest.mark.parametrize("bad", [{"frequency": "hourly"}, {"timezone": "Mars/Olympus"}, {"at_time": "25:99"}, {"weekday": "9"}])
def test_nonsense_is_a_400_not_a_crash(web, world, bad):
    form = {"frequency": "daily", "weekday": "0", "at_time": "03:00", "timezone": "Europe/Berlin",
            "recipient_user_id": str(world["admins"][world["first"]]), **bad}
    assert _post(web, "/settings/backup", **form).status_code == 400


def test_download_now_gives_this_workspaces_zip_only(web):
    response = _post(web, "/settings/backup/download-now")
    assert response.status_code == 200 and response.headers["content-type"] == "application/zip"
    assert 'attachment; filename="engcrm-backup-' in response.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(response.content)) as z:
        text = z.read("organizations.csv").decode("utf-8-sig")
    assert "Brandt" in text and "Kessler" not in text


def test_send_now_emails_the_signed_in_admin_and_keeps_a_copy(web, world):
    response = _post(web, "/settings/backup/send-now")
    assert response.status_code == 303
    (to, attachment), = web.sent
    assert to == "owner@first.example" and attachment[0].endswith(".zip")
    with workspace_scope(world["first"]):
        assert len(list_backup_files()) == 1


def test_a_kept_copy_downloads_but_never_from_another_workspace(web, world):
    deliver_backup(world["second"], sender=lambda *a, **k: True, trigger="manual",
                   recipient_user_id=world["admins"][world["second"]])
    with workspace_scope(world["second"]):
        foreign = list_backup_files()[0]["id"]
    assert web.get(f"/settings/backup/files/{foreign}").status_code == 404
    deliver_backup(world["first"], sender=lambda *a, **k: True, trigger="manual",
                   recipient_user_id=world["admins"][world["first"]])
    with workspace_scope(world["first"]):
        mine = list_backup_files()[0]["id"]
    ok = web.get(f"/settings/backup/files/{mine}")
    assert ok.status_code == 200 and ok.content[:2] == b"PK"


def test_every_backup_route_is_admin_only():
    """The whole router is guarded, so a route added later is admin-only too."""
    assert any(d.dependency is require_admin for d in backups.router.dependencies)
    assert backups.router.routes, "no routes to protect?"


def test_turning_it_off_clears_the_next_run(web, world):
    admin = world["admins"][world["first"]]
    with workspace_scope(world["first"]):
        save_schedule("daily", 0, time(3, 0), "Europe/Berlin", admin)
    _post(web, "/settings/backup", frequency="off", weekday="0", at_time="03:00", timezone="Europe/Berlin",
          recipient_user_id=str(admin))
    with workspace_scope(world["first"]):
        assert get_schedule()["next_run_at"] is None


def test_the_settings_page_shows_the_backup_section_to_a_signed_in_admin(world):
    from gcrm.api.security import hash_password
    with db() as connection:
        connection.cursor().execute("UPDATE users SET password_hash = %s WHERE id = %s",
                                    (hash_password("a-long-test-password-1"), world["admins"][world["first"]]))
    browser = TestClient(main.app)
    login = browser.post("/login", data={"email": "owner@first.example", "password": "a-long-test-password-1"},
                         follow_redirects=False)
    assert login.status_code in (302, 303), login.text[:200]
    with workspace_scope(world["first"]):
        save_schedule("weekly", 2, time(6, 30), "Europe/Berlin", world["admins"][world["first"]])
    page = browser.get("/settings?lang=en").text
    assert "Data backup" in page and 'value="06:30"' in page and "Email me a backup now" in page
    assert "owner@first.example" in page and "owner@second.example" not in page   # only this workspace's admins
