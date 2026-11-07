"""Settings → Data backup: schedule the automatic backups, send one now, download one.

Admin only. Every handler works inside the signed-in account's own workspace, and a kept
copy is looked up under that workspace's row security, so another workspace's backup is
simply not there (404), never forbidden-but-known.
"""
import logging
from datetime import datetime, time, timezone
from zoneinfo import available_timezones

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import Response

from gcrm.api.auth import require_admin, require_login
from gcrm.api.redirects import local_redirect
from gcrm.backup_export import build_backup
from gcrm.db.connection import db
from gcrm.tools.backup_schedule import (
    admin_recipients,
    deliver_backup,
    get_schedule,
    list_backup_files,
    read_backup_file,
    save_schedule,
)
from gcrm.tools.db_audit import log_audit
from gcrm.tools.email import send_backup_mail
from gcrm.workspace_context import workspace_scope

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/settings/backup", tags=["backup"],
                   dependencies=[Depends(require_login), Depends(require_admin)])

# A short, sensible list first; the full list stays available by typing.
COMMON_TIMEZONES = ("Europe/Berlin", "Europe/Vienna", "Europe/Zurich", "Europe/London", "Europe/Paris",
                    "Europe/Madrid", "Europe/Rome", "America/New_York", "America/Chicago",
                    "America/Los_Angeles", "Asia/Tokyo", "Australia/Sydney", "UTC")


def _workspace_id(request: Request) -> int:
    """The signed-in account's workspace; the shared admin login works in the default one."""
    workspace_id = request.session.get("workspace_id")
    if workspace_id is not None:
        return workspace_id
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM workspaces WHERE slug = 'default'")
        return cur.fetchone()["id"]


def _user_id(request: Request) -> int | None:
    return request.session.get("user_id")


def backup_context(workspace_id: int) -> dict:
    """What the Settings page shows for backups."""
    with workspace_scope(workspace_id):
        schedule = get_schedule()
        return {"schedule": schedule, "files": list_backup_files(), "recipients": admin_recipients(),
                "common_timezones": COMMON_TIMEZONES, "all_timezones": sorted(available_timezones())}


def _back(flag: str):
    return local_redirect("/settings", backup=flag)


@router.post("")
def save_backup_schedule(
    request: Request,
    frequency: str = Form(...),
    weekday: int = Form(0),
    at_time: str = Form("03:00"),
    timezone: str = Form("Europe/Berlin"),
    recipient_user_id: int | None = Form(None),
):
    """Set (or switch off) the automatic backups of this workspace."""
    try:
        when = time.fromisoformat(at_time.strip())
        with workspace_scope(_workspace_id(request)):
            save_schedule(frequency, weekday, when, timezone.strip(), recipient_user_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error) or "Invalid backup schedule")
    return _back("saved")


@router.post("/send-now")
def send_backup_now(request: Request):
    """Email a backup right now to the signed-in admin, without touching the schedule."""
    workspace_id = _workspace_id(request)
    with workspace_scope(workspace_id):
        recipient = _user_id(request) or get_schedule()["recipient_user_id"]
    result = deliver_backup(workspace_id, sender=send_backup_mail, trigger="manual", recipient_user_id=recipient)
    return _back({"sent": "sent", "link": "link"}.get(result["status"], "failed"))


@router.post("/download-now")
def download_backup_now(request: Request):
    """Build a backup and hand it to the browser; nothing is emailed or kept."""
    workspace_id = _workspace_id(request)
    now = datetime.now(timezone.utc)
    archive, _manifest = build_backup(workspace_id, now)
    log_audit(None, None, "backup.downloaded", f"workspace:{workspace_id}", "direct")
    return Response(archive, media_type="application/zip", headers={
        "Content-Disposition": f'attachment; filename="engcrm-backup-{now:%Y-%m-%d}.zip"',
        "Cache-Control": "no-store"})


@router.get("/files/{file_id}")
def download_kept_backup(request: Request, file_id: int):
    """One of the last kept backups of this workspace."""
    with workspace_scope(_workspace_id(request)):
        found = read_backup_file(file_id)
    if found is None:
        raise HTTPException(status_code=404, detail="Backup not found")
    filename, data = found
    log_audit(None, None, "backup.downloaded", f"backup:{file_id}", "kept copy")
    return Response(data, media_type="application/zip", headers={
        "Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"})
