"""Nodes for the evidence-backed opportunity-analysis graph."""

import logging

from langchain_core.messages import HumanMessage, SystemMessage

from gcrm.json_parsing import parse_llm_json

from .prompts import build_opportunity_prompt

logger = logging.getLogger(__name__)
_SCORE_FIELDS = ("opportunity_score", "confidence_score", "priority_score")


def initialize(state, dependencies) -> dict:
    limit = state.get("limit", 50)
    return {
        "run_id": dependencies.start_run("opportunity_agent", {"limit": limit}),
        "limit": limit,
        "contacts": [],
        "analyses": [],
        "errors": [],
        "analyzed_count": 0,
        "summary": "",
    }


def fetch_contacts(state, dependencies) -> dict:
    try:
        return {"contacts": dependencies.fetch_contacts(limit=state["limit"])}
    except Exception as error:
        return {"contacts": [], "errors": state["errors"] + [f"fetch failed: {error}"]}


def analyse_contacts(state, dependencies) -> dict:
    analyses, errors = [], list(state["errors"])
    for contact in state.get("contacts", []):
        try:
            analyses.append(_analyse_contact(contact, dependencies))
        except Exception as error:
            contact_id = contact.get("id", "unknown")
            logger.warning("opportunity analysis failed for %s: %s", contact_id, error)
            errors.append(f"contact {contact_id}: {error}")
    return {"analyses": analyses, "errors": errors}


def _analyse_contact(contact, dependencies) -> dict:
    interactions = dependencies.fetch_interactions(contact["id"])
    dossier = _get_dossier(contact, dependencies)
    system, user = build_opportunity_prompt(
        dependencies.mission,
        contact,
        interactions,
        dossier,
    )
    response = dependencies.llm.invoke([SystemMessage(content=system), HumanMessage(content=user)])
    analysis = _validate_analysis(parse_llm_json(response.content))
    return {"contact_id": contact["id"], "analysis": analysis}


def _get_dossier(contact, dependencies) -> dict | None:
    """Fetch or create a research dossier for the contact.
    Uses the injected get_or_create_dossier tool if available,
    falls back to legacy website fetch for backward compatibility."""
    if hasattr(dependencies, "get_or_create_dossier") and dependencies.get_or_create_dossier:
        try:
            return dependencies.get_or_create_dossier(contact["id"])
        except Exception as error:
            logger.info("dossier generation failed for %s: %s — falling back", contact["id"], error)
    # Legacy fallback: raw website fetch.
    website_content = _fetch_website_content(contact, dependencies)
    if website_content:
        return {
            "research_status": "legacy_fallback",
            "official_domain": "",
            "company_summary": website_content[:800],
            "evidence": [],
            "people": [],
            "person_context": [],
        }
    return None


def _fetch_website_content(contact, dependencies) -> str:
    website = contact.get("website")
    if not website:
        return "No website was available."
    try:
        return dependencies.fetch_page(website)[:4000]
    except Exception as error:
        logger.info("opportunity analysis could not fetch %s: %s", contact["id"], error)
        return "Website content could not be fetched."


def _validate_analysis(analysis: dict) -> dict:
    validated = {field: _score(analysis.get(field)) for field in _SCORE_FIELDS}
    validated["fit_reasoning"] = _text(analysis.get("fit_reasoning"))
    validated["suggested_approach"] = _text(analysis.get("suggested_approach"))
    validated["evidence"] = _strings(analysis.get("evidence"), maximum=5)
    validated["discovery_questions"] = _strings(analysis.get("discovery_questions"), maximum=5)
    validated["recommended_services"] = _services(analysis.get("recommended_services"))
    return validated


def _score(value) -> int:
    try:
        return max(0, min(100, int(value)))
    except (TypeError, ValueError):
        return 0


def _text(value) -> str:
    return str(value or "Insufficient evidence was available for a reliable assessment.").strip()


def _strings(value, maximum: int) -> list[str]:
    return [str(entry).strip() for entry in value or [] if str(entry).strip()][:maximum]


def _services(value) -> list[dict]:
    services = []
    for service in value or []:
        if not isinstance(service, dict) or not service.get("service"):
            continue
        services.append({
            "service": _text(service.get("service")),
            "outcome": _text(service.get("outcome")),
            "rationale": _text(service.get("rationale")),
        })
    return services[:3]


def save_analyses(state, dependencies) -> dict:
    saved = 0
    errors = list(state["errors"])
    for entry in state.get("analyses", []):
        try:
            dependencies.save_analysis(
                entry["contact_id"],
                entry["analysis"],
                dependencies.model_name,
            )
            saved += 1
        except Exception as error:
            errors.append(f"contact {entry['contact_id']}: save failed: {error}")
    return {"analyzed_count": saved, "errors": errors}


def generate_report(state, dependencies) -> dict:
    total = len(state.get("contacts", []))
    saved = state.get("analyzed_count", 0)
    errors = state.get("errors", [])
    summary = f"opportunity_agent: processed {total} contacts — {saved} analyses saved"
    if errors:
        summary += f", {len(errors)} error(s)"
    dependencies.finish_run(
        state.get("run_id", 0),
        "completed" if not errors else "completed_with_errors",
        summary,
        {"processed": total, "saved": saved, "errors": len(errors)},
    )
    return {"summary": summary}
