from typing import TypedDict


class EnrichmentState(TypedDict):
    # inputs
    limit: int

    # working state
    run_id: int
    contacts: list[dict]       # contacts fetched for enrichment
    results: list[dict]        # [{contact_id, website, email, phone, found}]
    errors: list[str]

    # output
    enriched_count: int
    not_found_count: int
    summary: str
