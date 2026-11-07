"""Scheduled backups on the real schema: who is due, what is sent to whom, what is kept,
and that a failure in one workspace never stops another."""
import io
import zipfile
from datetime import datetime, time, timedelta, timezone

import pytest

from gcrm.db.connection import db
from gcrm.tools import backup_schedule as schedule
from gcrm.tools.backup_schedule import (
    BACKUP_COPIES_KEPT,
    deliver_backup,
    get_schedule,
    list_backup_files,
    read_backup_file,
    run_due_backups,
    save_schedule,
)
from gcrm.tools.db_organizations import save_organization
from gcrm.workspace_context import workspace_scope

pytestmark = pytest.mark.integration

NOW = datetime(2026, 11, 7, 10, 0, tzinfo=timezone.utc)


class Outbox:
    """Stands in for the mail server."""

    def __init__(self, fail_for: set[str] | None = None):
        self.sent: list[dict] = []
        self.fail_for = fail_for or set()

    def __call__(self, to_email, subject, body, attachment=None):
        if to_email in self.fail_for:
            return False
        self.sent.append({"to": to_email, "subject": subject, "body": body, "attachment": attachment})
        return True


def _admin(workspace: int, email: str, role: str = "admin", active: bool = True) -> int:
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("INSERT INTO users (email, name, password_hash, role, workspace_id, is_active) "
                       "VALUES (%s, %s, 'x', %s, %s, %s) RETURNING id", (email, email.split("@")[0], role, workspace, active))
        return cursor.fetchone()["id"]


def _workspace(slug: str) -> int:
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("INSERT INTO workspaces (slug, name) VALUES (%s, %s) "
                       "ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name RETURNING id", (slug, slug))
        return cursor.fetchone()["id"]


@pytest.fixture
def world(clean_database, monkeypatch):
    monkeypatch.setattr("gcrm.tools.db_organizations.geocode", lambda city, country: None)
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug = 'default'")
        first = cursor.fetchone()["id"]
    second = _workspace("other-customer")
    a_admin = _admin(first, "owner@first.example")
    b_admin = _admin(second, "owner@second.example")
    with workspace_scope(first):
        save_organization("Brandt Maschinenbau", "Augsburg", source="test_fixture")
    with workspace_scope(second):
        save_organization("Kessler Logistik", "Ulm", source="test_fixture")
    return {"first": first, "second": second, "a_admin": a_admin, "b_admin": b_admin}


def _save(workspace: int, user: int, frequency="daily", now=NOW, **kw):
    with workspace_scope(workspace):
        return save_schedule(frequency=frequency, weekday=kw.get("weekday", 0), at_time=kw.get("at_time", time(3, 0)),
                             tz=kw.get("timezone", "Europe/Berlin"), recipient_user_id=user, now=now)


def test_a_workspace_starts_with_backups_off(world):
    with workspace_scope(world["first"]):
        assert get_schedule()["frequency"] == "off"


def test_saving_a_schedule_sets_the_next_run(world):
    saved = _save(world["first"], world["a_admin"])
    assert saved["frequency"] == "daily" and saved["next_run_at"] == datetime(2026, 11, 8, 2, 0, tzinfo=timezone.utc)
    off = _save(world["first"], world["a_admin"], frequency="off")
    assert off["next_run_at"] is None


def test_the_recipient_must_be_an_active_admin_of_that_workspace(world):
    spectator = _admin(world["first"], "viewer@first.example", role="spectator")
    gone = _admin(world["first"], "gone@first.example", active=False)
    for bad in (world["b_admin"], spectator, gone, 999999):  # another workspace's admin, a viewer, an inactive user, nobody
        with pytest.raises(ValueError):
            _save(world["first"], bad)


def test_only_the_due_workspace_is_backed_up_and_its_data_goes_to_its_own_admin(world):
    _save(world["first"], world["a_admin"], now=NOW - timedelta(days=2))   # due: next run was yesterday
    _save(world["second"], world["b_admin"], now=NOW)                      # not due until tomorrow
    outbox = Outbox()
    results = run_due_backups(now=NOW, sender=outbox)
    assert [r["workspace_id"] for r in results] == [world["first"]] and results[0]["status"] == "sent"
    (mail,) = outbox.sent
    assert mail["to"] == "owner@first.example"
    name, data = mail["attachment"]
    assert name.endswith(".zip")
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        text = z.read("organizations.csv").decode("utf-8-sig")
    assert "Brandt" in text and "Kessler" not in text
    with workspace_scope(world["first"]):
        assert get_schedule()["last_status"] == "sent"
        assert get_schedule()["next_run_at"] > NOW


def test_a_missed_run_is_made_up_once_not_repeated(world):
    _save(world["first"], world["a_admin"], now=NOW - timedelta(days=10))
    outbox = Outbox()
    run_due_backups(now=NOW, sender=outbox)
    run_due_backups(now=NOW + timedelta(minutes=1), sender=outbox)
    assert len(outbox.sent) == 1


def test_one_workspace_failing_never_stops_the_others_and_is_retried_in_an_hour(world):
    _save(world["first"], world["a_admin"], now=NOW - timedelta(days=2))
    _save(world["second"], world["b_admin"], now=NOW - timedelta(days=2))
    outbox = Outbox(fail_for={"owner@first.example"})
    results = {r["workspace_id"]: r["status"] for r in run_due_backups(now=NOW, sender=outbox)}
    assert results == {world["first"]: "failed", world["second"]: "sent"}
    with workspace_scope(world["first"]):
        failed = get_schedule()
        assert failed["last_status"] == "failed" and failed["next_run_at"] == NOW + timedelta(hours=1)


def test_an_error_while_building_is_recorded_and_isolated(world, monkeypatch):
    _save(world["first"], world["a_admin"], now=NOW - timedelta(days=2))
    _save(world["second"], world["b_admin"], now=NOW - timedelta(days=2))
    real = schedule.build_backup

    def flaky(workspace_id, *a, **k):
        if workspace_id == world["first"]:
            raise RuntimeError("disk full")
        return real(workspace_id, *a, **k)

    monkeypatch.setattr(schedule, "build_backup", flaky)
    outbox = Outbox()
    results = {r["workspace_id"]: r["status"] for r in run_due_backups(now=NOW, sender=outbox)}
    assert results == {world["first"]: "failed", world["second"]: "sent"}
    with workspace_scope(world["first"]):
        assert "disk full" in get_schedule()["last_error"]


def test_a_big_backup_goes_as_a_login_protected_link_instead_of_an_attachment(world, monkeypatch):
    monkeypatch.setattr(schedule, "MAX_ATTACHMENT_BYTES", 10)
    _save(world["first"], world["a_admin"], now=NOW - timedelta(days=2))
    outbox = Outbox()
    (result,) = run_due_backups(now=NOW, sender=outbox)
    assert result["status"] == "link"
    (mail,) = outbox.sent
    assert mail["attachment"] is None and "/settings" in mail["body"]


def test_copies_are_kept_per_workspace_newest_first_and_trimmed(world):
    _save(world["first"], world["a_admin"])
    _save(world["second"], world["b_admin"])
    for n in range(BACKUP_COPIES_KEPT + 3):
        deliver_backup(world["first"], now=NOW + timedelta(days=n), sender=Outbox())
    deliver_backup(world["second"], now=NOW, sender=Outbox())
    with workspace_scope(world["first"]):
        files = list_backup_files()
        assert len(files) == BACKUP_COPIES_KEPT
        assert files[0]["created_at"] > files[-1]["created_at"]
        assert read_backup_file(files[0]["id"])[1][:2] == b"PK"
        mine = {f["id"] for f in files}
    with workspace_scope(world["second"]):
        assert read_backup_file(next(iter(mine))) is None   # another workspace's copy is invisible
        assert len(list_backup_files()) == 1


def test_manual_send_does_not_move_the_schedule(world):
    saved = _save(world["first"], world["a_admin"])
    outbox = Outbox()
    deliver_backup(world["first"], now=NOW, sender=outbox, trigger="manual")
    assert len(outbox.sent) == 1
    with workspace_scope(world["first"]):
        assert get_schedule()["next_run_at"] == saved["next_run_at"]
