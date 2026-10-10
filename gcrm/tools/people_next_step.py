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
from gcrm.tools.deal_records import check_next_step, log_entry, write_next_step

__all__ = ["log_entry", "set_person_next_step"]


def set_person_next_step(person_id: int, text: str, due: date | None) -> dict | None:
    """Set the next step on the person's Consulting deal, or clear it with a blank
    `text` (a cleared step is logged as done). Saving what is already there
    writes nothing. A person with no Consulting deal yet gets one at candidate,
    so the step has a deal to live on. Returns {next_step, next_step_date,
    logged}, or None when the person does not exist. Raises ValueError for a date
    with no step, or a step over the length limit."""
    text = check_next_step(text, due)
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM people WHERE id = %s AND deleted_at IS NULL FOR UPDATE", (person_id,))
        if cur.fetchone() is None:
            return None
        deal = get_person_deal(cur, person_id)
        stored = ((deal or {}).get("next_step") or "").strip(), (deal or {}).get("next_step_date")
        if stored == (text, due):
            return {"next_step": text or None, "next_step_date": due, "logged": False}
        if deal is None:
            set_person_stage(cur, person_id, "candidate")
            deal = get_person_deal(cur, person_id)
        logged = write_next_step(cur, deal, text, due)
        cur.execute("UPDATE people SET updated_at = NOW() WHERE id = %s", (person_id,))
    log_audit(None, None, "person.next_step", f"person:{person_id}",
              ("next_step" if text else "next_step_done") if logged else "cleared")
    return {"next_step": text or None, "next_step_date": due, "logged": logged}
