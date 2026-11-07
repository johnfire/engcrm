"""Scheduled data backups: when one is due, who gets it, what is kept.

The export itself is gcrm/backup_export.py. This module decides *when* and *where to*:
each workspace has one schedule (off / daily / weekly at a time in its own time zone) and
a recipient who must be an active admin of that workspace. A background loop looks at each
workspace in turn, inside that workspace's scope, so one workspace's problem never stops
another's backup and no workspace can read another's schedule or copies.

The backup is attached to the email, so the customer keeps it even if the website is gone.
Over MAX_ATTACHMENT_BYTES the email carries a login-protected link instead.
"""
import logging
import os
import threading
import time as clock
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from gcrm.backup_export import build_backup
from gcrm.config import APP_PUBLIC_URL
from gcrm.db.connection import db, serialize_row
from gcrm.i18n import translate as t
from gcrm.tools.db_audit import log_audit
from gcrm.tools.email import send_backup_mail
from gcrm.workspace_context import workspace_scope

logger = logging.getLogger(__name__)

FREQUENCIES = ("off", "daily", "weekly")
BACKUP_COPIES_KEPT = 7
RETRY_AFTER = timedelta(hours=1)
CHECK_EVERY_SECONDS = 60
MAX_ATTACHMENT_BYTES = int(float(os.getenv("BACKUP_MAX_ATTACHMENT_MB", "10")) * 1024 * 1024)


def compute_next_run(frequency: str, weekday: int, at_time: time, tz: str, after: datetime) -> datetime | None:
    """The first moment strictly after `after` that matches the schedule in time zone `tz`
    (UTC out). None when off. Raises ValueError for nonsense."""
    if frequency not in FREQUENCIES:
        raise ValueError(f"unknown frequency {frequency!r}")
    if not 0 <= int(weekday) <= 6:
        raise ValueError("weekday must be 0 (Monday) to 6 (Sunday)")
    try:
        zone = ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        raise ValueError(f"unknown time zone {tz!r}")
    if frequency == "off":
        return None
    local = after.astimezone(zone)
    for ahead in range(0, 9):
        day = (local + timedelta(days=ahead)).date()
        if frequency == "weekly" and day.weekday() != int(weekday):
            continue
        candidate = datetime.combine(day, at_time.replace(tzinfo=None), tzinfo=zone).astimezone(timezone.utc)
        if candidate > after:
            return candidate
    raise ValueError("no run found")  # unreachable: a matching day always falls within 8 days


# --- The schedule row (inside a workspace scope) ---------------------------------

def get_schedule() -> dict:
    """This workspace's schedule; backups are off until an admin sets one."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT frequency, weekday, at_time, timezone, recipient_user_id, next_run_at, last_run_at, "
                    "last_status, last_error FROM backup_schedules")
        row = cur.fetchone()
    if row is None:
        return {"frequency": "off", "weekday": 0, "at_time": time(3, 0), "timezone": "Europe/Berlin",
                "recipient_user_id": None, "next_run_at": None, "last_run_at": None,
                "last_status": None, "last_error": None}
    return dict(row)


def admin_recipients() -> list[dict]:
    """Active admins of this workspace: the only people a backup can be sent to."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, email, name, ui_language FROM users WHERE role = 'admin' AND is_active "
                    "AND deleted_at IS NULL ORDER BY id")
        return [dict(row) for row in cur.fetchall()]


def save_schedule(frequency: str, weekday: int, at_time: time, tz: str, recipient_user_id: int | None,
                  now: datetime | None = None) -> dict:
    """Set the schedule. The recipient must be an active admin of this workspace.
    Raises ValueError for a stranger as recipient, or a nonsense frequency, weekday or time zone."""
    now = now or datetime.now(timezone.utc)
    next_run = compute_next_run(frequency, weekday, at_time, tz, now)
    if frequency != "off" and recipient_user_id not in {admin["id"] for admin in admin_recipients()}:
        raise ValueError("the recipient must be an active admin of this workspace")
    if frequency == "off" and recipient_user_id is not None and \
            recipient_user_id not in {admin["id"] for admin in admin_recipients()}:
        recipient_user_id = None
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO backup_schedules (workspace_id, frequency, weekday, at_time, timezone, recipient_user_id, "
            "next_run_at, updated_at) VALUES (request_workspace_id(), %s, %s, %s, %s, %s, %s, NOW()) "
            "ON CONFLICT (workspace_id) DO UPDATE SET frequency = EXCLUDED.frequency, weekday = EXCLUDED.weekday, "
            "at_time = EXCLUDED.at_time, timezone = EXCLUDED.timezone, recipient_user_id = EXCLUDED.recipient_user_id, "
            "next_run_at = EXCLUDED.next_run_at, updated_at = NOW()",
            (frequency, weekday, at_time, tz, recipient_user_id, next_run),
        )
    log_audit(None, None, "backup.schedule_saved", None, f"{frequency} {weekday} {at_time:%H:%M} {tz}")
    return get_schedule()


# --- Kept copies (inside a workspace scope) --------------------------------------

def list_backup_files() -> list[dict]:
    """This workspace's kept backups, newest first (without their content)."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, filename, size_bytes, kind, created_at FROM backup_files "
                    "WHERE workspace_id = request_workspace_id() ORDER BY created_at DESC, id DESC")
        return [serialize_row(dict(row)) | {"created_at": row["created_at"]} for row in cur.fetchall()]


def read_backup_file(file_id: int) -> tuple[str, bytes] | None:
    """(filename, ZIP bytes) of one kept backup of this workspace, or None."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT filename, content FROM backup_files WHERE id = %s AND workspace_id = request_workspace_id()",
                    (file_id,))
        row = cur.fetchone()
    return (row["filename"], bytes(row["content"])) if row else None


def _store_copy(filename: str, archive: bytes, manifest: dict, kind: str, now: datetime) -> None:
    import json
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO backup_files (workspace_id, filename, size_bytes, content, manifest, kind, created_at) "
            "VALUES (request_workspace_id(), %s, %s, %s, %s, %s, %s)",
            (filename, len(archive), archive, json.dumps(manifest), kind, now),
        )
        cur.execute(
            "DELETE FROM backup_files WHERE workspace_id = request_workspace_id() AND id NOT IN ("
            "SELECT id FROM backup_files WHERE workspace_id = request_workspace_id() "
            "ORDER BY created_at DESC, id DESC LIMIT %s)", (BACKUP_COPIES_KEPT,))


# --- Making and sending one -------------------------------------------------------

def _recipient(recipient_user_id: int | None) -> dict:
    admins = {admin["id"]: admin for admin in admin_recipients()}
    wanted = recipient_user_id if recipient_user_id is not None else get_schedule()["recipient_user_id"]
    if wanted not in admins:
        raise ValueError("no active admin of this workspace to send the backup to")
    return admins[wanted]


def _message(language: str, now: datetime, counts: dict, attached: bool) -> tuple[str, str]:
    rows = sum(counts.values())
    key = "backup.email.bodyAttached" if attached else "backup.email.bodyLink"
    return (t("backup.email.subject", language, date=f"{now:%d.%m.%Y}"),
            t(key, language, date=f"{now:%d.%m.%Y}", rows=rows, url=f"{APP_PUBLIC_URL}/settings"))


def _record_result(workspace_id: int, now: datetime, status: str, error: str | None, kind: str) -> None:
    """Remember how the last run went; a failed scheduled run is retried in an hour."""
    retry = now + RETRY_AFTER if (status == "failed" and kind == "scheduled") else None
    try:
        with workspace_scope(workspace_id), db() as conn:
            conn.cursor().execute(
                "UPDATE backup_schedules SET last_run_at = %s, last_status = %s, last_error = %s, "
                "next_run_at = COALESCE(%s, next_run_at) WHERE workspace_id = %s",
                (now, status, error, retry, workspace_id))
    except Exception:
        logger.exception("could not record the backup result for workspace %s", workspace_id)


def deliver_backup(workspace_id: int, now: datetime | None = None, sender=send_backup_mail,
                   trigger: str = "scheduled", recipient_user_id: int | None = None) -> dict:
    """Build the workspace's backup, keep a copy, and email it (attached, or as a link when
    big). Never raises: the outcome is returned and recorded on the schedule."""
    now = now or datetime.now(timezone.utc)
    status, error = "failed", None
    try:
        with workspace_scope(workspace_id):
            recipient = _recipient(recipient_user_id)
            archive, manifest = build_backup(workspace_id, now)
            filename = f"engcrm-backup-{now:%Y-%m-%d}.zip"
            _store_copy(filename, archive, manifest, trigger, now)
            attach = len(archive) <= MAX_ATTACHMENT_BYTES
            subject, body = _message(recipient.get("ui_language") or "en", now, manifest["counts"], attach)
            if sender(recipient["email"], subject, body, (filename, archive) if attach else None):
                status = "sent" if attach else "link"
            else:
                error = "the mail server did not accept the message"
            log_audit(None, None, "backup.delivered", f"workspace:{workspace_id}", f"{trigger} {status}")
    except Exception as exc:
        logger.exception("backup failed for workspace %s", workspace_id)
        error = (str(exc) or exc.__class__.__name__)[:500]
    _record_result(workspace_id, now, status, error, trigger)
    return {"workspace_id": workspace_id, "status": status, "error": error}


# --- The loop ----------------------------------------------------------------------

def _claim_if_due(now: datetime) -> bool:
    """Atomically take this workspace's due run and move the schedule on, so a run that was
    missed is made up once and two loops can never both send it."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT frequency, weekday, at_time, timezone FROM backup_schedules "
                    "WHERE frequency <> 'off' AND next_run_at <= %s FOR UPDATE", (now,))
        row = cur.fetchone()
        if row is None:
            return False
        following = compute_next_run(row["frequency"], row["weekday"], row["at_time"], row["timezone"], now)
        cur.execute("UPDATE backup_schedules SET next_run_at = %s WHERE workspace_id = request_workspace_id()",
                    (following,))
    return True


def _workspace_ids() -> list[int]:
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM workspaces ORDER BY id")
        return [row["id"] for row in cur.fetchall()]


def run_due_backups(now: datetime | None = None, sender=send_backup_mail) -> list[dict]:
    """Back up every workspace whose time has come. Each is handled on its own: a failure in
    one is recorded and logged, and the others still run."""
    now = now or datetime.now(timezone.utc)
    results = []
    for workspace_id in _workspace_ids():
        try:
            with workspace_scope(workspace_id):
                due = _claim_if_due(now)
            if due:
                results.append(deliver_backup(workspace_id, now, sender, "scheduled"))
        except Exception:
            logger.exception("backup check failed for workspace %s", workspace_id)
            results.append({"workspace_id": workspace_id, "status": "failed", "error": "check failed"})
    return results


def _backup_loop() -> None:
    while True:
        try:
            run_due_backups()
        except Exception:
            logger.exception("backup check failed; trying again in a minute")
        clock.sleep(CHECK_EVERY_SECONDS)


def start_backup_loop() -> threading.Thread:
    """Check for due backups once a minute in the background of the running app."""
    thread = threading.Thread(target=_backup_loop, daemon=True, name="scheduled-backups")
    thread.start()
    return thread
