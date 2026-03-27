from typing import TypedDict


class OutreachState(TypedDict):
    # --- inputs ---
    limit: int          # max contacts to process per run

    # --- working state ---
    run_id: int
    contacts: list[dict]
    drafts: list[dict]  # [{contact_id, subject, body, blocked_reason}]
    errors: list[str]

    # --- output ---
    queued_count: int
    blocked_count: int
    summary: str
