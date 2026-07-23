"""Erasure and retention enforcement for personal CRM data."""
from pathlib import Path

from gcrm.config import (
    AGENT_RUN_RETENTION_DAYS,
    AUDIT_LOG_RETENTION_DAYS,
    CARD_IMAGE_DIR,
    CONTACT_RETENTION_DAYS,
    INBOX_RETENTION_DAYS,
    PUSH_TOKEN_RETENTION_DAYS,
)
from gcrm.db.connection import db
from gcrm.tools.db_audit import log_audit


def _remove_card_images(image_paths: list[str]) -> int:
    """Delete captured-card files only when their stored filename is safe."""
    base_directory = Path(CARD_IMAGE_DIR).resolve()
    deleted_count = 0
    for image_path in image_paths:
        candidate = (base_directory / image_path).resolve()
        if candidate.parent != base_directory:
            continue
        if candidate.is_file():
            candidate.unlink()
            deleted_count += 1
    return deleted_count


def _delete_contact_rows(cursor, contact_id: int) -> list[str]:
    """Remove data linked to one contact and return its card-image filenames."""
    cursor.execute(
        "DELETE FROM card_captures WHERE contact_id = %s OR dup_contact_id = %s RETURNING image_path",
        (contact_id, contact_id),
    )
    image_paths = [row["image_path"] for row in cursor.fetchall() if row["image_path"]]
    cursor.execute("DELETE FROM outreach_outcomes WHERE contact_id = %s", (contact_id,))
    cursor.execute(
        "DELETE FROM people WHERE linked_contact_id = %s OR contact_id = %s",
        (contact_id, contact_id),
    )
    cursor.execute("DELETE FROM inbox_messages WHERE matched_contact_id = %s", (contact_id,))
    cursor.execute("DELETE FROM contacts WHERE id = %s", (contact_id,))
    return image_paths


def erase_contact(contact_id: int) -> bool:
    """Permanently erase a contact and all directly linked personal data."""
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM contacts WHERE id = %s", (contact_id,))
        if cursor.fetchone() is None:
            return False
        image_paths = _delete_contact_rows(cursor, contact_id)
    removed_images = _remove_card_images(image_paths)
    log_audit(None, None, "contact.erased", f"contact:{contact_id}", f"images_removed:{removed_images}")
    return True


def _delete_expired_rows(
    cursor,
    table: str,
    timestamp_column: str,
    retention_days: int,
    condition: str = "TRUE",
) -> int:
    """Delete rows older than the configured retention period."""
    cursor.execute(
        f"DELETE FROM {table} WHERE {condition} AND {timestamp_column} < NOW() - (%s * INTERVAL '1 day')",
        (retention_days,),
    )
    return cursor.rowcount


def purge_expired_data() -> dict[str, int]:
    """Apply the documented retention periods and return auditable counts."""
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT contact_id FROM consent_log WHERE erasure_requested = TRUE")
        erasure_ids = [row["contact_id"] for row in cursor.fetchall()]
        cursor.execute(
            "SELECT id FROM contacts WHERE created_at < NOW() - (%s * INTERVAL '1 day')",
            (CONTACT_RETENTION_DAYS,),
        )
        expired_contact_ids = [row["id"] for row in cursor.fetchall()]

    contact_ids = list(dict.fromkeys([*erasure_ids, *expired_contact_ids]))
    erased_contact_ids = {contact_id for contact_id in contact_ids if erase_contact(contact_id)}
    with db() as connection:
        cursor = connection.cursor()
        counts = {
            "contacts": sum(contact_id in expired_contact_ids for contact_id in erased_contact_ids),
            "inbox_messages": _delete_expired_rows(
                cursor,
                "inbox_messages",
                "received_at",
                INBOX_RETENTION_DAYS,
                "matched_contact_id IS NULL",
            ),
            "agent_runs": _delete_expired_rows(
                cursor,
                "agent_runs",
                "COALESCE(finished_at, started_at)",
                AGENT_RUN_RETENTION_DAYS,
            ),
            "push_tokens": _delete_expired_rows(cursor, "push_tokens", "updated_at", PUSH_TOKEN_RETENTION_DAYS),
            "audit_log": _delete_expired_rows(cursor, "audit_log", "at", AUDIT_LOG_RETENTION_DAYS),
        }
    counts["erasure_requests"] = sum(contact_id in erasure_ids for contact_id in erased_contact_ids)
    log_audit(None, None, "privacy.retention_purged", "privacy-retention", str(counts))
    return counts
