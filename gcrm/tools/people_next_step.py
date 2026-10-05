"""What happens next with a person: one current step (and an optional due date)
on the person, with every change also written to their note log so the history
of what was planned stays.

Log entries are language-neutral data, labelled by the UI through their method:
`next_step` holds the step ("invite to coffee (2026-10-15)"), `next_step_done`
marks a step that was cleared ("✓ invite to coffee").
"""
from datetime import date

from gcrm.db.connection import db
from gcrm.tools.db_audit import log_audit

MAX_LENGTH = 500
LOG_METHOD = "next_step"
DONE_METHOD = "next_step_done"


def log_entry(text: str, due: date | None) -> str:
    return f"{text} ({due.isoformat()})" if due else text


def set_person_next_step(person_id: int, text: str, due: date | None) -> dict | None:
    """Set the person's next step, or clear it with a blank `text` (a cleared step
    is logged as done). Saving what is already there writes nothing. Returns
    {next_step, next_step_date, logged}, or None when the person does not exist.
    Raises ValueError for a date with no step, or a step over MAX_LENGTH."""
    text = (text or "").strip()
    if len(text) > MAX_LENGTH:
        raise ValueError(f"a next step is at most {MAX_LENGTH} characters")
    if not text and due is not None:
        raise ValueError("a due date needs a next step")
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT next_step, next_step_date FROM people WHERE id = %s AND deleted_at IS NULL FOR UPDATE",
            (person_id,),
        )
        current = cur.fetchone()
        if current is None:
            return None
        previous = (current["next_step"] or "").strip()
        if (previous, current["next_step_date"]) == (text, due):
            return {"next_step": text or None, "next_step_date": due, "logged": False}
        cur.execute(
            "UPDATE people SET next_step = %s, next_step_date = %s, updated_at = NOW() WHERE id = %s",
            (text or None, due, person_id),
        )
        entry = (LOG_METHOD, log_entry(text, due)) if text else (DONE_METHOD, f"✓ {previous}")
        logged = bool(text or previous)
        if logged:
            cur.execute(
                "INSERT INTO people_interactions (person_id, method, note) VALUES (%s, %s, %s)",
                (person_id, *entry),
            )
    log_audit(None, None, "person.next_step", f"person:{person_id}", entry[0] if logged else "cleared")
    return {"next_step": text or None, "next_step_date": due, "logged": logged}
