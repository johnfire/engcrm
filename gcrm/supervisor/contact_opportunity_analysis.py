"""Run one evidence-backed opportunity assessment from a contact detail page."""
from gcrm.config import ACTIVE_MISSION, CHEAP_LLM, RESEARCH_DOSSIER_ENABLED
from gcrm.tools import (
    fetch_page,
    finish_run,
    get_contact_interactions,
    get_llm,
    save_opportunity_analysis,
    start_run,
)
from gcrm.tools.db_contacts import get_contact


def analyse_contact_opportunity(contact_id: int) -> dict:
    """Analyse one active contact, including contacts assessed in an earlier run."""
    contact = get_contact(contact_id)
    if not contact or contact.get("deleted_at"):
        raise LookupError("Contact not found")

    from gcrm_opportunity_agent import create_opportunity_agent

    from gcrm.research import get_or_create_dossier

    agent = create_opportunity_agent(
        llm=get_llm(CHEAP_LLM),
        fetch_contacts=lambda limit: [contact],
        fetch_interactions=get_contact_interactions,
        fetch_page=fetch_page,
        get_or_create_dossier=get_or_create_dossier if RESEARCH_DOSSIER_ENABLED else None,
        save_analysis=save_opportunity_analysis,
        start_run=start_run,
        finish_run=finish_run,
        mission=ACTIVE_MISSION,
        model_name=CHEAP_LLM,
    )
    return agent.invoke({"limit": 1})
