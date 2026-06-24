from typing import TypedDict


class FollowupState(TypedDict):
    # --- working state ---
    run_id: int
    inbox_messages: list[dict]      # raw unprocessed messages from inbox

    # [{message_id, contact_id, classification, draft_subject?, draft_body?, to_email?}]
    classified_replies: list[dict]

    overdue_contacts: list[dict]

    errors: list[str]

    # --- output ---
    queued_count: int
    opt_out_count: int
    warm_count: int         # warm replies — flagged for visit_when_nearby
    bounce_count: int       # delivery failures detected and marked as bad_email
    summary: str
