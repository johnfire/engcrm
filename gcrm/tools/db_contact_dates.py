"""Actual contact days and corrections backed by interaction history."""
from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from gcrm.activity_types import NOT_ACTIVITIES
from gcrm.db.connection import db, serialize_row
from gcrm.tools.db_audit import log_audit

CONTACT_TIMEZONE = "Europe/Berlin"
CONTACT_TABLES = {
    "organization": ("contacts", "interactions", "contact_id", "interaction_date", "summary"),
    "person": ("people", "people_interactions", "person_id", "occurred_at", "note"),
}
# A next-step change records a plan, rather than contact with the person.
PLAN_METHODS_SQL = ", ".join(f"'{method}'" for method in NOT_ACTIVITIES)
CONTACT_HISTORY_FILTER = f"deleted_at IS NULL AND COALESCE(method, '') NOT IN ({PLAN_METHODS_SQL})"


def contact_tables(kind: str) -> tuple[str, ...]:
    if kind not in CONTACT_TABLES:
        raise HTTPException(400, "Unknown contact type")
    return CONTACT_TABLES[kind]


def contact_day_sql(kind: str, column: str) -> str:
    """Identifiers are constants owned by callers, never submitted fields."""
    return f"({column} AT TIME ZONE '{CONTACT_TIMEZONE}')::date" if kind == "person" else column


def parse_contact_day(value: str) -> date:
    try:
        if len(value) != 10:
            raise ValueError()
        selected = date.fromisoformat(value)
        if selected.isoformat() != value:
            raise ValueError()
    except ValueError as failure:
        raise HTTPException(400, "Contact date must be YYYY-MM-DD") from failure
    if selected > datetime.now(ZoneInfo(CONTACT_TIMEZONE)).date():
        raise HTTPException(400, "Contact date cannot be in the future")
    return selected


def require_contact(cursor, kind: str, contact_id: int, workspace_id: int | None, *, lock=False) -> dict:
    parent, *_ = contact_tables(kind)
    scope = " AND workspace_id=%s" if workspace_id is not None else ""
    cursor.execute(f"SELECT id,name FROM {parent} WHERE id=%s AND deleted_at IS NULL{scope}"
                   + (" FOR UPDATE" if lock else ""),
                   [contact_id] + ([workspace_id] if workspace_id is not None else []))
    record = cursor.fetchone()
    if not record:
        raise HTTPException(404, "Contact not found")
    return dict(record)


def latest_contact(cursor, kind: str, contact_id: int) -> dict:
    _, history, foreign_key, timestamp, _ = contact_tables(kind)
    day = contact_day_sql(kind, timestamp)
    cursor.execute(f"SELECT id AS interaction_id, {day} AS contact_date FROM {history} "
                   f"WHERE {foreign_key}=%s AND {CONTACT_HISTORY_FILTER} "
                   f"ORDER BY {timestamp} DESC, id DESC LIMIT 1", (contact_id,))
    row = cursor.fetchone()
    return serialize_row(dict(row)) if row else {"interaction_id": None, "contact_date": None}


def get_contact_date(kind: str, contact_id: int, workspace_id: int | None) -> dict:
    with db() as connection:
        cursor = connection.cursor()
        record = require_contact(cursor, kind, contact_id, workspace_id)
        return {**record, "kind": kind, **latest_contact(cursor, kind, contact_id)}


def write_contact_day(cursor, kind: str, contact_id: int, selected: date, interaction_id: int | None) -> None:
    parent, history, foreign_key, timestamp, note_column = contact_tables(kind)
    if interaction_id is None:
        stamp = f"(%s::date + TIME '12:00') AT TIME ZONE '{CONTACT_TIMEZONE}'" if kind == "person" else "%s"
        cursor.execute(f"INSERT INTO {history} ({foreign_key}, {timestamp}, method, {note_column}) "
                       f"VALUES (%s, {stamp}, 'other', %s)",
                       (contact_id, selected, "Contact recorded manually"))
    else:
        stamp = (f"(%s::date + ({timestamp} AT TIME ZONE '{CONTACT_TIMEZONE}')::time) "
                 f"AT TIME ZONE '{CONTACT_TIMEZONE}'") if kind == "person" else "%s"
        cursor.execute(f"UPDATE {history} SET {timestamp}={stamp} WHERE id=%s AND {foreign_key}=%s",
                       (selected, interaction_id, contact_id))
    cursor.execute(f"UPDATE {parent} SET updated_at=NOW() WHERE id=%s", (contact_id,))


def set_contact_date(kind: str, contact_id: int, selected: date, interaction_id: int | None,
                     previous_date: str | None, workspace_id: int | None) -> dict:
    """Correct the reviewed interaction; reject stale forms rather than guessing."""
    with db() as connection:
        cursor = connection.cursor()
        record = require_contact(cursor, kind, contact_id, workspace_id, lock=True)
        current = latest_contact(cursor, kind, contact_id)
        if current != {"interaction_id": interaction_id, "contact_date": previous_date}:
            raise HTTPException(409, "Contact history changed. Reopen the date editor and try again.")
        write_contact_day(cursor, kind, contact_id, selected, interaction_id)
        updated = {**record, "kind": kind, **latest_contact(cursor, kind, contact_id)}
    log_audit(None, None, "contact.date_changed", f"{kind}:{contact_id}",
              f"interaction:{interaction_id or updated['interaction_id']} {previous_date or 'unrecorded'}->{selected.isoformat()}")
    return updated
