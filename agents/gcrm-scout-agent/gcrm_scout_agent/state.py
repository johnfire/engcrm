from typing import TypedDict


class ScoutState(TypedDict):
    # --- inputs ---
    limit: int          # max candidates to process per run

    # --- working state ---
    run_id: int
    candidates: list[dict]       # all candidates fetched
    gallery_candidates: list[dict]  # galleries only, with website_content added
    scores: list[dict]           # [{contact_id, outcome, reasoning}]
    errors: list[str]

    # --- output ---
    promoted_count: int
    maybe_count: int
    dropped_count: int
    summary: str
