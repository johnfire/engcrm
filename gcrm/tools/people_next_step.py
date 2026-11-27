"""What happens next with a person, on their Consulting deal — the phone's
next-step field, from before a person could have deals for several offers.
Every change is also written to their note log so the history of plans stays;
gcrm/tools/deal_records.py does the writing, for this and for every other deal.

Log entries are language-neutral data, labelled by the UI through their method:
`next_step` holds the step ("invite to coffee (2026-10-15)"), `next_step_done`
marks a step that was cleared ("✓ invite to coffee").
"""
from datetime import date

from gcrm.db.connection import db
from gcrm.tools.db_audit import log_audit
from gcrm.tools.db_deals import get_person_deal, set_person_stage
from gcrm.tools.deal_records import (
    TASK_TYPES,
    check_next_step,
    log_entry,
    write_next_step,
)

__all__ = ["log_entry", "set_person_next_step"]


def set_person_next_step(person_id: int, text: str, due: date | None, *, task_type: str | None = None) -> dict | None:
    """Add a next step to the person's Consulting deal, or with a blank `text` mark
    the earliest open one done (a cleared step is logged as done). Earlier steps are
    never rewritten, and saving what is already there writes nothing. A person with
    no Consulting deal yet gets one at candidate, so the step has a deal to live on.
    Returns {next_step, next_step_date, logged} as the deal shows them afterwards, or
    None when the person does not exist. Raises ValueError for a date with no step,
    or a step over the length limit."""
    text = check_next_step(text, due)
    if task_type is not None and task_type not in TASK_TYPES:
        raise ValueError("Choose Commitment or Check-in")
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM people WHERE id = %s AND deleted_at IS NULL FOR UPDATE", (person_id,))
        if cur.fetchone() is None:
            return None
        deal = get_person_deal(cur, person_id)
        if deal is not None:
            cur.execute("SELECT id FROM deals WHERE id=%s FOR UPDATE", (deal["id"],))
            deal = get_person_deal(cur, person_id)
        if deal is None:
            if not text:
                return {"next_step": None, "next_step_date": None, "logged": False}
            set_person_stage(cur, person_id, "candidate")
            deal = get_person_deal(cur, person_id)
        change = write_next_step(cur, deal, text, due, task_type)
        cur.execute("SELECT next_step, next_step_date FROM deals WHERE id=%s", (deal["id"],))
        current = cur.fetchone()
        if change is not None:
            cur.execute("UPDATE people SET updated_at = NOW() WHERE id = %s", (person_id,))
    logged = change is not None and change.logged
    if change is not None:
        log_audit(None, None, "person.next_step", f"person:{person_id}",
                  ("next_step" if text else "next_step_done") if logged else "cleared")
    return {"next_step": current["next_step"], "next_step_date": current["next_step_date"], "logged": logged}
