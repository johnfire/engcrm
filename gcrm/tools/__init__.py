"""
Concrete tool implementations injected into agents at runtime.
Each function satisfies a Protocol defined in the relevant agent repo.
"""
from .db import (
    save_contact,
    get_candidates,
    get_cold_contacts,
    update_contact,
    get_contacts_needing_enrichment,
    update_contact_details,
    check_compliance,
    ensure_consent_log,
    queue_for_approval,
    log_interaction,
    get_contact_interactions,
    set_opt_out,
    get_overdue_contacts,
    save_inbox_message,
    get_unprocessed_inbox,
    mark_message_processed,
    match_contact_by_email,
    start_run,
    finish_run,
    get_next_research_targets,
    mark_research_target_done,
    get_cities,
    add_city,
    get_city_market_context,
    update_city_market,
    get_city_scan_status,
    get_all_city_scan_status,
    record_scan_result,
    can_run_level,
)
from .search import web_search, geo_search, google_maps_search, fetch_page
from .email import send_email, read_inbox
from .llm import get_llm

__all__ = [
    "save_contact", "get_candidates", "get_cold_contacts", "update_contact",
    "get_contacts_needing_enrichment", "update_contact_details",
    "check_compliance", "ensure_consent_log", "queue_for_approval",
    "log_interaction", "get_contact_interactions", "set_opt_out", "get_overdue_contacts",
    "save_inbox_message", "get_unprocessed_inbox", "mark_message_processed",
    "match_contact_by_email", "start_run", "finish_run",
    "get_next_research_targets", "mark_research_target_done",
    "get_cities", "add_city", "get_city_market_context", "update_city_market",
    "get_city_scan_status", "get_all_city_scan_status",
    "record_scan_result", "can_run_level",
    "web_search", "geo_search", "google_maps_search", "fetch_page",
    "send_email", "read_inbox",
    "get_llm",
]
