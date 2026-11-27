"""The history line a next step leaves on its owner. Language-neutral data, labelled by the UI through its
method: `next_step` holds the step ("invite to coffee (2026-10-15)"), `next_step_done` marks one finished
("✓ invite to coffee")."""
from datetime import date

LOG_METHOD, DONE_METHOD = "next_step", "next_step_done"


def log_entry(text: str, due: date | None) -> str:
    return f"{text} ({due.isoformat()})" if due else text


def log_step_on_owner(cur, deal: dict, method: str, note: str) -> None:
    """Write the line to the notes of the deal's person, or the history of its organization."""
    if deal["person_id"] is not None:
        cur.execute(
            "INSERT INTO people_interactions (person_id, method, note, offer_id) VALUES (%s, %s, %s, %s)",
            (deal["person_id"], method, note, deal["offer_id"]),
        )
    else:
        cur.execute(
            "INSERT INTO interactions (contact_id, interaction_date, method, summary, offer_id, workspace_id) "
            "SELECT id, CURRENT_DATE, %s, %s, %s, workspace_id FROM contacts WHERE id = %s",
            (method, note, deal["offer_id"], deal["contact_id"]),
        )
