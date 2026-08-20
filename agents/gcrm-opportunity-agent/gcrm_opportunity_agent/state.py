from typing import TypedDict


class OpportunityState(TypedDict):
    limit: int
    run_id: int
    organizations: list[dict]
    analyses: list[dict]
    errors: list[str]
    analyzed_count: int
    summary: str
