"""
Concrete tool implementations injected into agents at runtime.
Each function satisfies a Protocol defined in the relevant agent repo.
"""
from .db import (
    add_city,
    can_run_level,
    check_compliance,
    ensure_consent_log,
    finish_run,
    get_all_city_scan_status,
    get_candidates,
    get_cities,
    get_city_market_context,
    get_city_scan_status,
    get_contact_interactions,
    get_contacts_needing_enrichment,
    get_contacts_ready_for_outreach,
    get_existing_contact_names,
    get_ignored_chains,
    get_outreach_outcomes,
    get_overdue_contacts,
    get_run_costs,
    get_unprocessed_inbox,
    log_interaction,
    mark_bad_email,
    mark_message_processed,
    match_contact_by_email,
    queue_for_approval,
    record_scan_result,
    record_warm_outcome,
    save_contact,
    save_inbox_classification,
    save_inbox_message,
    set_contact_state,
    set_opt_out,
    set_suppression_flag,
    set_visit_when_nearby,
    start_run,
    update_city_market,
    update_contact_details,
)
from .db_opportunities import (
    get_contacts_needing_opportunity_analysis,
    get_latest_opportunity_analysis,
    save_opportunity_analysis,
)
from .email import read_inbox, send_email
from .llm import get_llm
from .memory import capture_thought, search_gcrm_thoughts
from .search import fetch_page, geo_search, google_maps_search, web_search

__all__ = [
    "save_contact", "get_existing_contact_names", "get_candidates",
    "get_contacts_ready_for_outreach", "set_contact_state", "set_suppression_flag",
    "get_contacts_needing_enrichment", "update_contact_details",
    "get_contacts_needing_opportunity_analysis", "get_latest_opportunity_analysis",
    "save_opportunity_analysis",
    "check_compliance", "ensure_consent_log", "queue_for_approval",
    "log_interaction", "get_contact_interactions", "set_opt_out", "get_overdue_contacts",
    "save_inbox_message", "get_unprocessed_inbox", "mark_message_processed",
    "match_contact_by_email", "start_run", "finish_run",
    "get_cities", "add_city", "get_city_market_context", "update_city_market",
    "get_city_scan_status", "get_all_city_scan_status",
    "record_scan_result", "can_run_level",
    "web_search", "geo_search", "google_maps_search", "fetch_page",
    "send_email", "read_inbox",
    "get_llm",
    "capture_thought", "search_gcrm_thoughts",
    "record_warm_outcome", "get_outreach_outcomes",
    "get_ignored_chains", "mark_bad_email", "set_visit_when_nearby",
    "save_inbox_classification", "get_run_costs",
]
