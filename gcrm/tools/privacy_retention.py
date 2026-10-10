"""Erasure and retention enforcement for personal CRM data."""
from pathlib import Path

from gcrm.config import (
    AGENT_RUN_RETENTION_DAYS,
    AUDIT_LOG_RETENTION_DAYS,
    CARD_IMAGE_DIR,
    CONTACT_RETENTION_DAYS,
    INBOX_RETENTION_DAYS,
    PEOPLE_RETENTION_DAYS,
    PUSH_TOKEN_RETENTION_DAYS,
)
from gcrm.db.connection import db
from gcrm.linkedin import linkedin_url_hash
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


def _delete_organization_rows(cursor, contact_id: int) -> list[str]:
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


def erase_organization(contact_id: int) -> bool:
    """Permanently erase a contact and all directly linked personal data."""
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM contacts WHERE id = %s", (contact_id,))
        if cursor.fetchone() is None:
            return False
        image_paths = _delete_organization_rows(cursor, contact_id)
    removed_images = _remove_card_images(image_paths)
    log_audit(None, None, "contact.erased", f"contact:{contact_id}", f"images_removed:{removed_images}")
    return True


def erase_person(person_id: int, suppress_reimport: bool = True) -> bool:
    """Permanently delete one person. Everything that points at them (notes,
    ratings, queued drafts, rejected matches) goes with them by cascade.

    With `suppress_reimport`, a person who has a LinkedIn URL leaves behind only
    its hash, so the next Connections.csv import skips them instead of quietly
    re-adding them. Returns False when there is no such person."""
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT linkedin_url FROM people WHERE id = %s", (person_id,))
        row = cursor.fetchone()
        if row is None:
            return False
        suppressed = False
        url_hash = linkedin_url_hash(row["linkedin_url"]) if suppress_reimport else None
        if url_hash:
            cursor.execute(
                "INSERT INTO person_import_suppressions (linkedin_url_hash) VALUES (%s) "
                "ON CONFLICT DO NOTHING",
                (url_hash,),
            )
            suppressed = True
        cursor.execute("DELETE FROM people WHERE id = %s", (person_id,))
    log_audit(None, None, "person.erased", f"person:{person_id}", "suppressed" if suppressed else "erased")
    return True


def _purge_expired_people(cursor) -> int:
    """Delete people nobody has touched for PEOPLE_RETENTION_DAYS, plus anything
    already soft-deleted. Only people not linked to an organization: linked ones
    go with their organization. People marked "keep" are exempt from the age rule.

    "Touched" is the latest of: created, edited (which includes a re-import),
    last note, last rating, last queued draft, last change to a deal they own."""
    cursor.execute(
        """
        DELETE FROM people p
        WHERE p.deleted_at IS NOT NULL
           OR (
                p.contact_id IS NULL AND p.linked_contact_id IS NULL AND NOT p.retention_hold
                AND GREATEST(
                    p.created_at,
                    p.updated_at,
                    (SELECT MAX(occurred_at) FROM people_interactions WHERE person_id = p.id),
                    (SELECT MAX(updated_at)  FROM person_user_priorities WHERE person_id = p.id),
                    (SELECT MAX(created_at)  FROM approval_queue WHERE person_id = p.id),
                    (SELECT MAX(updated_at)  FROM deals WHERE person_id = p.id)
                ) < NOW() - (%s * INTERVAL '1 day')
           )
        """,
        (PEOPLE_RETENTION_DAYS,),
    )
    return cursor.rowcount


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
    erased_contact_ids = {contact_id for contact_id in contact_ids if erase_organization(contact_id)}
    with db() as connection:
        cursor = connection.cursor()
        counts = {
            "people": _purge_expired_people(cursor),
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
