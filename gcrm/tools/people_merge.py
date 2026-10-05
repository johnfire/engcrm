"""Merge a duplicate person into the one that stays.

Nothing the duplicate knows is lost: blank fields on the kept person are filled
from the duplicate, flags such as `retention_hold` are kept if either row set
them, both notes are kept, and where both rows hold *different* values the kept
person's value stays and the duplicate's is written into the notes. Every row
that points at the duplicate — interaction notes, drafts, ratings, rejected
company matches — is moved to the kept person before the duplicate is deleted.

The duplicate is deleted rather than soft-deleted on purpose: the LinkedIn
import matches people by URL and email without looking at `deleted_at`, so a
soft-deleted twin would keep catching re-imports. The before-image of both
people and every moved row is returned so the caller can store it.
"""
from datetime import date

from gcrm.db.connection import db, serialize_row
from gcrm.tools.db_audit import log_audit

# Columns that describe the row rather than the person.
_ROW_COLUMNS = {"id", "created_at", "updated_at", "deleted_at", "workspace_id"}

# Every table with a foreign key to people(id), and how a clash on the kept
# person is resolved. An unlisted table stops the merge: moving rows blindly
# could hit a unique constraint, and deleting the duplicate would cascade away
# whatever was not moved.
_CHILD_TABLES = {
    ("people_interactions", "person_id"): None,
    ("approval_queue", "person_id"): None,
    # One rating per user: the kept person's rating wins, the other is noted.
    ("person_user_priorities", "person_id"): "user_id",
    # "Does not work at X" — the same fact twice is one fact.
    ("person_match_rejections", "person_id"): "contact_id",
}


class MergeRefused(Exception):
    """The merge needs a human decision; nothing was written."""


def _is_blank(value) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def plan_field_merge(keep: dict, drop: dict, today: date) -> tuple[dict, list[str]]:
    """The column updates for the kept person, and the duplicate's differing
    values that could not be stored in a column (they go into the notes)."""
    updates: dict = {}
    conflicts: list[str] = []
    for column, drop_value in drop.items():
        keep_value = keep.get(column)
        if column in _ROW_COLUMNS or column == "notes" or _is_blank(drop_value):
            continue
        if isinstance(drop_value, bool):
            if drop_value and not keep_value:
                updates[column] = True
        elif _is_blank(keep_value):
            updates[column] = drop_value
        elif str(keep_value).strip().lower() != str(drop_value).strip().lower():
            conflicts.append(f"{column}: {drop_value}")

    if keep.get("created_at") and drop.get("created_at") and drop["created_at"] < keep["created_at"]:
        updates["created_at"] = drop["created_at"]

    merged_notes = _merge_notes(keep.get("notes"), drop.get("notes"), conflicts, drop["id"], today)
    if merged_notes != keep.get("notes"):
        updates["notes"] = merged_notes
    return updates, conflicts


def _merge_notes(keep_notes, drop_notes, conflicts: list[str], drop_id: int, today: date):
    if _is_blank(drop_notes) and not conflicts:
        return keep_notes
    lines = [f"[Merged from person #{drop_id} on {today.isoformat()}]"]
    if conflicts:
        lines.append(f"Other values #{drop_id} had: " + "; ".join(conflicts))
    if not _is_blank(drop_notes) and drop_notes.strip() != (keep_notes or "").strip():
        lines.append(drop_notes.strip())
    block = "\n".join(lines)
    return block if _is_blank(keep_notes) else f"{keep_notes.rstrip()}\n\n{block}"


def _child_tables(cur) -> list[tuple[str, str]]:
    cur.execute(
        "SELECT c.conrelid::regclass::text AS tbl, a.attname AS col "
        "FROM pg_constraint c "
        "JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey) "
        "WHERE c.contype = 'f' AND c.confrelid = 'people'::regclass "
        "ORDER BY 1, 2"
    )
    found = [(row["tbl"], row["col"]) for row in cur.fetchall()]
    unknown = [ref for ref in found if ref not in _CHILD_TABLES]
    if unknown:
        raise MergeRefused(f"tables reference people that the merge does not handle: {unknown}")
    return found


def _move_children(cur, table: str, column: str, keep_id: int, drop_id: int) -> tuple[list, list]:
    """Move the duplicate's rows; return (moved before-image, clashing rows left behind)."""
    cur.execute(f"SELECT * FROM {table} WHERE {column} = %s", (drop_id,))
    rows = [serialize_row(dict(r)) for r in cur.fetchall()]
    clash_key = _CHILD_TABLES[(table, column)]
    clashes: list = []
    if clash_key:
        cur.execute(
            f"SELECT d.* FROM {table} d WHERE d.{column} = %s AND EXISTS "
            f"(SELECT 1 FROM {table} k WHERE k.{column} = %s AND k.{clash_key} = d.{clash_key})",
            (drop_id, keep_id),
        )
        clashes = [serialize_row(dict(r)) for r in cur.fetchall()]
        cur.execute(
            f"DELETE FROM {table} d WHERE d.{column} = %s AND EXISTS "
            f"(SELECT 1 FROM {table} k WHERE k.{column} = %s AND k.{clash_key} = d.{clash_key})",
            (drop_id, keep_id),
        )
    cur.execute(f"UPDATE {table} SET {column} = %s WHERE {column} = %s", (keep_id, drop_id))
    return rows, clashes


def _load_pair(cur, keep_id: int, drop_id: int) -> tuple[dict, dict]:
    if keep_id == drop_id:
        raise MergeRefused("a person cannot be merged into themselves")
    cur.execute("SELECT * FROM people WHERE id IN (%s, %s) FOR UPDATE", (keep_id, drop_id))
    by_id = {row["id"]: dict(row) for row in cur.fetchall()}
    missing = [pid for pid in (keep_id, drop_id) if pid not in by_id]
    if missing:
        raise MergeRefused(f"no person with id {missing}")
    keep, drop = by_id[keep_id], by_id[drop_id]
    if keep.get("deleted_at") or drop.get("deleted_at"):
        raise MergeRefused("one of the two people is soft-deleted")
    if keep.get("workspace_id") != drop.get("workspace_id"):
        raise MergeRefused("the two people belong to different workspaces")
    return keep, drop


def merge_people(keep_id: int, drop_id: int, apply: bool = False, today: date | None = None) -> dict:
    """Merge person `drop_id` into `keep_id` in one transaction.

    With apply=False everything is computed inside the transaction and then
    rolled back, so the preview is exactly what --apply would write."""
    today = today or date.today()
    with db() as conn:
        cur = conn.cursor()
        keep, drop = _load_pair(cur, keep_id, drop_id)
        updates, conflicts = plan_field_merge(keep, drop, today)
        moved, clashes = {}, {}
        for table, column in _child_tables(cur):
            rows, left = _move_children(cur, table, column, keep_id, drop_id)
            moved[table], clashes[table] = rows, left
            if table == "person_user_priorities" and left:
                updates["notes"] = _note_rating_clash(updates.get("notes", keep.get("notes")), left)
        if updates:
            assignments = ", ".join(f"{col} = %s" for col in updates)
            cur.execute(
                f"UPDATE people SET {assignments}, updated_at = NOW() WHERE id = %s",
                [*updates.values(), keep_id],
            )
        cur.execute("DELETE FROM people WHERE id = %s AND name = %s", (drop_id, drop["name"]))
        if cur.rowcount != 1:
            raise MergeRefused(f"person #{drop_id} changed while merging")
        if not apply:
            conn.rollback()

    report = {
        "keep": serialize_row(keep),
        "drop": serialize_row(drop),
        "updates": serialize_row(updates),
        "conflicts": conflicts,
        "moved": moved,
        "clashes_dropped": clashes,
        "applied": apply,
    }
    if apply:
        log_audit(None, None, "person.merge", f"person:{keep_id}", f"merged person:{drop_id}")
    return report


def _note_rating_clash(notes, clashes: list) -> str:
    detail = "; ".join(f"user {row['user_id']} rated #{row['person_id']} {row['priority']}" for row in clashes)
    return f"{(notes or '').rstrip()}\nRating not carried over (kept person already rated): {detail}"
