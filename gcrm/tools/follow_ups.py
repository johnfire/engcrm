"""Persistence for independently managed commitments and check-ins."""
from datetime import date

from gcrm.db.connection import db
from gcrm.tools.db_audit import log_audit

TASK_TYPES = ("commitment", "check_in")


def validate_task(task_type: str, task_text: str) -> str:
    text = (task_text or "").strip()
    if task_type not in TASK_TYPES:
        raise ValueError("Choose Commitment or Check-in")
    if not text or len(text) > 500:
        raise ValueError("Follow-up text must be between 1 and 500 characters")
    return text


def refresh_deal_projection(cursor, deal_id: int) -> None:
    """Keep old readers pointed at the earliest active task for this deal."""
    cursor.execute(
        """
        UPDATE deals SET (next_step, next_step_date) = (
            SELECT task_text, due_date FROM follow_ups
             WHERE deal_id = %s AND status = 'active'
             ORDER BY due_date ASC NULLS LAST, id LIMIT 1
        ) WHERE id = %s
        """, (deal_id, deal_id),
    )


def record_unclassified_deal_step(cursor, deal_id: int, text: str, due_date: date | None) -> int | None:
    """Retain an old client's new step for review, without guessing its type."""
    cursor.execute("SELECT id FROM follow_ups WHERE deal_id=%s AND status='review' "
                   "AND (source_kind='deal' OR source_kind IS NULL) ORDER BY id LIMIT 1 FOR UPDATE", (deal_id,))
    review = cursor.fetchone()
    if review is not None:
        if text:
            cursor.execute("UPDATE follow_ups SET task_text=%s, due_date=%s, updated_at=clock_timestamp() "
                           "WHERE id=%s", (text, due_date, review["id"]))
        else:
            cursor.execute("UPDATE follow_ups SET status='completed', completed_at=NOW(), updated_at=clock_timestamp() "
                           "WHERE id=%s", (review["id"],))
        return review["id"]
    elif text:
        cursor.execute(
            """INSERT INTO follow_ups (workspace_id, contact_id, person_id, contact_person_id, deal_id,
                                       task_text, due_date, source_kind, source_id, source_date)
               SELECT workspace_id, contact_id, person_id, contact_person_id, id, %s, %s,
                      CASE WHEN EXISTS (SELECT 1 FROM follow_ups WHERE source_kind='deal' AND source_id=%s)
                           THEN NULL ELSE 'deal' END,
                      CASE WHEN EXISTS (SELECT 1 FROM follow_ups WHERE source_kind='deal' AND source_id=%s)
                           THEN NULL ELSE id END, CURRENT_DATE
                 FROM deals WHERE id=%s RETURNING id""", (text, due_date, deal_id, deal_id, deal_id),
        )
        return cursor.fetchone()["id"]
    return None


def record_activity_follow_up(cursor, interaction_id: int, task_type: str | None,
                              capture_snapshot: bool = False) -> dict | None:
    """Create a task in the same transaction as its source activity."""
    if task_type is not None and task_type not in TASK_TYPES:
        raise ValueError("Choose Commitment or Check-in")
    cursor.execute(
        """INSERT INTO follow_ups (workspace_id, contact_id, deal_id, task_text, due_date,
                                   task_type, status, source_kind, source_id, source_date)
           SELECT i.workspace_id, i.contact_id, d.id, COALESCE(i.next_action, ''), i.next_action_date,
                  %s, CASE WHEN %s IS NOT NULL AND NULLIF(trim(i.next_action), '') IS NOT NULL
                           THEN 'active' ELSE 'review' END, 'interaction', i.id, i.interaction_date
             FROM interactions i
             LEFT JOIN deals d ON d.contact_id=i.contact_id AND d.offer_id=i.offer_id
                              AND d.workspace_id=i.workspace_id AND d.deleted_at IS NULL
            WHERE i.id=%s AND (NULLIF(trim(i.next_action), '') IS NOT NULL OR i.next_action_date IS NOT NULL)
           ON CONFLICT DO NOTHING RETURNING id, updated_at""", (task_type, task_type, interaction_id),
    )
    if not capture_snapshot:
        return None
    row = cursor.fetchone()
    return {"id": row["id"], "version": row["updated_at"].isoformat()} if row else None


def create_follow_up(*, task_type: str, task_text: str, due_date: date | None = None,
                     deal_id: int | None = None, contact_id: int | None = None, person_id: int | None = None,
                     contact_person_id: int | None = None, workspace_id: int | None = None) -> int:
    text = validate_task(task_type, task_text)
    with db() as connection:
        cursor = connection.cursor()
        if deal_id is not None:
            cursor.execute("SELECT * FROM deals WHERE id=%s AND deleted_at IS NULL FOR UPDATE", (deal_id,))
            deal = cursor.fetchone()
            if deal is None or (workspace_id is not None and deal["workspace_id"] != workspace_id):
                raise ValueError("Deal not found")
            if contact_id is not None and contact_id != deal["contact_id"]:
                raise ValueError("Deal does not belong to this organization")
            if person_id is not None and person_id != deal["person_id"]:
                raise ValueError("Deal does not belong to this person")
            contact_id, person_id = deal["contact_id"], deal["person_id"]
            contact_person_id = contact_person_id or deal["contact_person_id"]
        if (contact_id is None) == (person_id is None):
            raise ValueError("Choose one organization or person")
        owner_table = "contacts" if contact_id is not None else "people"
        cursor.execute(f"SELECT workspace_id FROM {owner_table} WHERE id=%s AND deleted_at IS NULL",
                       (contact_id if contact_id is not None else person_id,))
        owner = cursor.fetchone()
        if owner is None or (workspace_id is not None and owner["workspace_id"] != workspace_id):
            raise ValueError("Owner not found")
        if contact_person_id is not None:
            cursor.execute("SELECT 1 FROM people WHERE id=%s AND contact_id=%s AND workspace_id=%s "
                           "AND deleted_at IS NULL", (contact_person_id, contact_id, owner["workspace_id"]))
            if cursor.fetchone() is None:
                raise ValueError("Person does not belong to this organization")
        cursor.execute(
            """INSERT INTO follow_ups (workspace_id, contact_id, person_id, contact_person_id, deal_id,
                                       task_type, task_text, due_date, status)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'active') RETURNING id""",
            (owner["workspace_id"], contact_id, person_id, contact_person_id, deal_id, task_type, text, due_date),
        )
        task_id = cursor.fetchone()["id"]
        if deal_id is not None:
            refresh_deal_projection(cursor, deal_id)
    log_audit(None, None, "follow_up.created", f"follow_up:{task_id}", "active")
    return task_id


def list_follow_ups(workspace_id: int | None = None) -> list[dict]:
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT * FROM follow_ups WHERE status='active' AND (%s IS NULL OR workspace_id=%s) "
                       "ORDER BY due_date ASC NULLS LAST, id", (workspace_id, workspace_id))
        return [dict(row) for row in cursor.fetchall()]


def lock_task_deal(cursor, task_id: int, workspace_id: int | None, new_deal_id: int | None = None) -> None:
    """Take the deal lock before the task lock, matching legacy writes."""
    cursor.execute("SELECT deal_id FROM follow_ups WHERE id=%s AND (%s IS NULL OR workspace_id=%s)",
                   (task_id, workspace_id, workspace_id))
    task = cursor.fetchone()
    deal_ids = {deal for deal in (task["deal_id"] if task else None, new_deal_id) if deal is not None}
    if deal_ids:
        cursor.execute("SELECT id FROM deals WHERE id=ANY(%s) ORDER BY id FOR UPDATE", (sorted(deal_ids),))


def validate_association(cursor, task: dict, deal_id: int | None, contact_person_id: int | None) -> None:
    if deal_id is not None:
        cursor.execute("SELECT 1 FROM deals WHERE id=%s AND workspace_id=%s AND deleted_at IS NULL "
                       "AND contact_id IS NOT DISTINCT FROM %s AND person_id IS NOT DISTINCT FROM %s",
                       (deal_id, task["workspace_id"], task["contact_id"], task["person_id"]))
        if cursor.fetchone() is None:
            raise ValueError("Deal does not belong to this owner")
    if contact_person_id is not None:
        cursor.execute("SELECT 1 FROM people WHERE id=%s AND workspace_id=%s AND contact_id=%s "
                       "AND deleted_at IS NULL", (contact_person_id, task["workspace_id"], task["contact_id"]))
        if cursor.fetchone() is None:
            raise ValueError("Person does not belong to this organization")


def update_follow_up(task_id: int, *, task_type: str, task_text: str, due_date: date | None,
                     version, deal_id: int | None = -1, contact_person_id: int | None = -1,
                     workspace_id: int | None = None) -> None:
    text = validate_task(task_type, task_text)
    with db() as connection:
        cursor = connection.cursor()
        lock_task_deal(cursor, task_id, workspace_id, deal_id if deal_id != -1 else None)
        cursor.execute("SELECT * FROM follow_ups WHERE id=%s AND status='active' AND updated_at=%s "
                       "AND (%s IS NULL OR workspace_id=%s) FOR UPDATE", (task_id, version, workspace_id, workspace_id))
        task = cursor.fetchone()
        if task is None:
            raise ValueError("Follow-up changed or is unavailable; reload and try again")
        chosen_deal = task["deal_id"] if deal_id == -1 else deal_id
        chosen_person = task["contact_person_id"] if contact_person_id == -1 else contact_person_id
        validate_association(cursor, task, chosen_deal, chosen_person)
        cursor.execute(
            """UPDATE follow_ups SET task_type=%s, task_text=%s, due_date=%s, deal_id=%s,
                                     contact_person_id=%s, updated_at=clock_timestamp() WHERE id=%s""",
            (task_type, text, due_date, chosen_deal, chosen_person, task_id),
        )
        for affected_deal in {task["deal_id"], chosen_deal} - {None}:
            refresh_deal_projection(cursor, affected_deal)
    log_audit(None, None, "follow_up.updated", f"follow_up:{task_id}", "updated")


def change_follow_up_status(task_id: int, status: str, version, workspace_id: int | None = None) -> None:
    if status not in ("completed", "dismissed"):
        raise ValueError("Unknown follow-up status")
    with db() as connection:
        cursor = connection.cursor()
        lock_task_deal(cursor, task_id, workspace_id)
        cursor.execute("SELECT deal_id FROM follow_ups WHERE id=%s AND status='active' "
                       "AND updated_at=%s AND (%s IS NULL OR workspace_id=%s) FOR UPDATE",
                       (task_id, version, workspace_id, workspace_id))
        task = cursor.fetchone()
        if task is None:
            raise ValueError("Follow-up changed or is unavailable; reload and try again")
        cursor.execute("UPDATE follow_ups SET status=%s, updated_at=clock_timestamp(), "
                       "completed_at=CASE WHEN %s='completed' THEN NOW() END, "
                       "dismissed_at=CASE WHEN %s='dismissed' THEN NOW() END WHERE id=%s",
                       (status, status, status, task_id))
        if task["deal_id"] is not None:
            refresh_deal_projection(cursor, task["deal_id"])
    log_audit(None, None, "follow_up.status_changed", f"follow_up:{task_id}", status)


def undo_legacy_follow_up(deal_id: int, snapshot: dict, workspace_id: int) -> None:
    """Restore only the task the MCP changed, refusing intervening changes."""
    if snapshot.get("unchanged"):
        return
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM deals WHERE id=%s AND workspace_id=%s AND deleted_at IS NULL FOR UPDATE",
                       (deal_id, workspace_id))
        if cursor.fetchone() is None:
            raise ValueError("Deal is unavailable")
        cursor.execute("SELECT id FROM follow_ups WHERE id=%s AND deal_id=%s AND workspace_id=%s "
                       "AND updated_at=%s::timestamptz FOR UPDATE",
                       (snapshot["task_id"], deal_id, workspace_id, snapshot["after_version"]))
        if cursor.fetchone() is None:
            raise ValueError("Follow-up changed after this action; it cannot be undone safely")
        before = snapshot.get("task_before")
        if before is None:
            cursor.execute("UPDATE follow_ups SET status='dismissed', dismissed_at=NOW(), "
                           "updated_at=clock_timestamp() WHERE id=%s", (snapshot["task_id"],))
        else:
            cursor.execute("UPDATE follow_ups SET status=%s, task_text=%s, due_date=%s, completed_at=%s, "
                           "dismissed_at=%s, updated_at=clock_timestamp() WHERE id=%s",
                           (before["status"], before["task_text"], before["due_date"], before["completed_at"],
                            before["dismissed_at"], snapshot["task_id"]))
        cursor.execute("SELECT 1 FROM follow_ups WHERE deal_id=%s AND status='active' LIMIT 1", (deal_id,))
        if cursor.fetchone():
            refresh_deal_projection(cursor, deal_id)
        else:
            cursor.execute("UPDATE deals SET next_step=%s, next_step_date=%s WHERE id=%s",
                           (snapshot["next_step"], snapshot["next_step_date"], deal_id))
    log_audit(None, None, "follow_up.undo", f"follow_up:{snapshot['task_id']}", "restored")


def undo_activity_follow_up(contact_id: int, interaction_id: int, snapshot: dict | None,
                            workspace_id: int) -> None:
    """Undo an activity and its unchanged promise together."""
    with db() as connection:
        cursor = connection.cursor()
        if snapshot:
            lock_task_deal(cursor, snapshot["id"], workspace_id)
        cursor.execute("SELECT id, deal_id, updated_at FROM follow_ups WHERE source_kind='interaction' "
                       "AND source_id=%s AND workspace_id=%s FOR UPDATE", (interaction_id, workspace_id))
        task = cursor.fetchone()
        if task and (not snapshot or task["id"] != snapshot["id"] or
                     task["updated_at"].isoformat() != snapshot["version"]):
            raise ValueError("The activity's follow-up changed and cannot be undone safely")
        if snapshot and not task:
            raise ValueError("The activity's follow-up is unavailable")
        cursor.execute("UPDATE interactions SET deleted_at=NOW() WHERE id=%s AND contact_id=%s "
                       "AND workspace_id=%s AND deleted_at IS NULL RETURNING id",
                       (interaction_id, contact_id, workspace_id))
        if cursor.fetchone() is None:
            raise ValueError("The activity is unavailable")
        if task:
            cursor.execute("UPDATE follow_ups SET status='dismissed', dismissed_at=NOW(), "
                           "updated_at=clock_timestamp() WHERE id=%s", (task["id"],))
            if task["deal_id"] is not None:
                refresh_deal_projection(cursor, task["deal_id"])
    log_audit(None, None, "interaction.note_undone", f"contact:{contact_id}", str(interaction_id))


def resolve_review(task_id: int, decision: str, version, *, task_type: str = "", task_text: str = "",
                   due_date: date | None = None, linked_task_id: int | None = None,
                   deal_id: int | None = -1, contact_person_id: int | None = -1,
                   workspace_id: int | None = None) -> None:
    if decision not in ("keep", "dismiss", "link"):
        raise ValueError("Unknown review decision")
    if decision == "keep":
        task_text = validate_task(task_type, task_text)
    with db() as connection:
        cursor = connection.cursor()
        lock_task_deal(cursor, task_id, workspace_id, deal_id if deal_id != -1 else None)
        cursor.execute("SELECT * FROM follow_ups WHERE id=%s AND status='review' "
                       "AND updated_at=%s AND (%s IS NULL OR workspace_id=%s) FOR UPDATE",
                       (task_id, version, workspace_id, workspace_id))
        task = cursor.fetchone()
        if task is None:
            raise ValueError("Follow-up changed or is unavailable; reload and try again")
        chosen_deal = task["deal_id"] if deal_id == -1 else deal_id
        chosen_person = task["contact_person_id"] if contact_person_id == -1 else contact_person_id
        if decision == "keep":
            validate_association(cursor, task, chosen_deal, chosen_person)
        if decision == "link":
            cursor.execute("SELECT id FROM follow_ups WHERE id=%s AND id<>%s AND workspace_id=%s "
                           "AND contact_id IS NOT DISTINCT FROM %s AND person_id IS NOT DISTINCT FROM %s "
                           "AND status <> 'linked'", (linked_task_id, task_id, task["workspace_id"],
                                                       task["contact_id"], task["person_id"]))
            if cursor.fetchone() is None:
                raise ValueError("Linked follow-up must belong to the same owner")
        status = {"keep": "active", "dismiss": "dismissed", "link": "linked"}[decision]
        cursor.execute("UPDATE follow_ups SET status=%s, task_type=%s, task_text=%s, due_date=%s, "
                       "deal_id=%s, contact_person_id=%s, "
                       "linked_task_id=%s, dismissed_at=CASE WHEN %s='dismissed' THEN NOW() END, "
                       "updated_at=clock_timestamp() WHERE id=%s",
                       (status, task_type if decision == "keep" else task["task_type"],
                        task_text if decision == "keep" else task["task_text"],
                        due_date if decision == "keep" else task["due_date"],
                        chosen_deal if decision == "keep" else task["deal_id"],
                        chosen_person if decision == "keep" else task["contact_person_id"],
                        linked_task_id if decision == "link" else None, status, task_id))
        if decision == "keep":
            for affected_deal in {task["deal_id"], chosen_deal} - {None}:
                refresh_deal_projection(cursor, affected_deal)
    log_audit(None, None, "follow_up.reviewed", f"follow_up:{task_id}", status)
