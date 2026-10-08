"""Persist a reviewed profile without replacing a previously saved identity."""
from gcrm.db.connection import db
from gcrm.tools.capture_linkedin import normalize_profile_url
from gcrm.tools.db_audit import log_audit
from gcrm.workspace_context import get_workspace_id


def save_capture_profile(person_id: int, value: str) -> None:
    canonical = normalize_profile_url(value)
    if not canonical:
        raise ValueError("Enter a LinkedIn person profile URL (linkedin.com/in/...).")
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute(
            "UPDATE people SET linkedin_url=%s, updated_at=NOW() "
            "WHERE id=%s AND workspace_id=COALESCE(%s, "
            "(SELECT id FROM workspaces WHERE slug='default')) "
            "AND (NULLIF(linkedin_url, '') IS NULL OR linkedin_url=%s)",
            (canonical, person_id, get_workspace_id(), canonical),
        )
        if cursor.rowcount != 1:
            raise ValueError("This person already has a different LinkedIn profile. Review their existing record.")
    log_audit(None, None, "person.linkedin_saved", f"person:{person_id}", "capture_review_confirmed")
