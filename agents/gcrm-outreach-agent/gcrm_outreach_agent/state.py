from typing import TypedDict


class OutreachState(TypedDict):
    # --- inputs ---
    limit: int          # max contacts to process per run
    learnings: list[str]  # style notes from Open Brain, empty list if none

    # --- working state ---
    run_id: int
    organizations: list[dict]
    drafts: list[dict]  # [{contact_id, subject, body, blocked_reason}]
    errors: list[str]

    # --- output ---
    queued_count: int
    blocked_count: int
    summary: str
