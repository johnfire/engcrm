"""Draft the one-off, non-sales "curiosity" first-contact email for a
specific person. Mirrors gcrm/tools/email_extract.py's pattern (small LLM
call, tolerant JSON parsing, fixed client-safe error string on failure) but
assembles the final email from a fixed template — only the one-sentence
observation is LLM-authored. See
docs/plans/2026-08-26-person-curiosity-email-design.md.
"""
import logging

from gcrm.json_parsing import parse_llm_json
from gcrm.prompts.curiosity_email import draft_curiosity_observation_prompt

logger = logging.getLogger(__name__)

# What the web client is told when generation fails. Deliberately free of
# detail — the diagnosable version is in the server log.
DRAFT_FAILED = "Could not draft this email. Try again, or write it by hand."

CURIOSITY_TEMPLATES = {
    "en": {
        "greeting": "Hi {first_name},",
        "opening": (
            "My name is Christopher Rehm and I'm building an AI focused business, "
            "to assist businesses improve their regular workflows so they can "
            "focus on the key parts of their operation. I'm not open yet — I'll "
            "be starting October 1, 2026."
        ),
        "ask": "I'd love to know: how do you think AI will change work in {field} over the next few years?",
        "closing": "Happy to hear your thoughts whenever's convenient — no pitch, no obligation.",
        "signoff": "Best,\nChristopher Rehm",
        "subject": "Curious how you see AI affecting {field}",
        "field_fallback": "your line of work",
    },
    "de": {
        "greeting": "Hallo {first_name},",
        "opening": (
            "Mein Name ist Christopher Rehm, und ich baue gerade ein auf KI "
            "fokussiertes Unternehmen auf, das Unternehmen dabei hilft, ihre "
            "laufenden Arbeitsabläufe zu verbessern, damit sie sich auf die "
            "wichtigsten Teile ihres Betriebs konzentrieren können. Ich bin noch "
            "nicht im Geschäft — ich starte am 1. Oktober 2026."
        ),
        "ask": "Ich würde mich sehr über Ihre Einschätzung freuen: Wie wird KI aus Ihrer Sicht die Arbeit in {field} in den nächsten Jahren verändern?",
        "closing": "Ich freue mich über Ihre Gedanken, wann immer es Ihnen passt — kein Angebot, keine Verpflichtung.",
        "signoff": "Beste Grüße,\nChristopher Rehm",
        "subject": "Ihre Einschätzung zu KI in {field}",
        "field_fallback": "Ihrem Bereich",
    },
}


def _content_to_text(content) -> str:
    """ChatAnthropic .content is usually a str, but can be a list of blocks."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block.get("text", "") if isinstance(block, dict) else str(block) for block in content
        )
    return str(content)


def _field_label(person: dict, organization: dict | None, template: dict) -> str:
    if organization and organization.get("type"):
        return organization["type"]
    if person.get("title"):
        return person["title"]
    return template["field_fallback"]


def draft_curiosity_email(person_id: int, language: str = "en") -> dict:
    """
    Assemble the curiosity first-contact email for one person.

    Loads the person, their linked organization (if any), and their recent
    dictated interaction notes; generates the one-sentence observation via
    the LLM; and fills the fixed CURIOSITY_TEMPLATES[language] around it.

    Returns {"subject": str, "body": str} on success, or
    {"error": DRAFT_FAILED} on any generation failure — the real exception
    goes to the log. Raises LookupError if the person doesn't exist.
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    from gcrm.config import SMART_LLM
    from gcrm.tools.db_organizations import get_organization
    from gcrm.tools.db_people import get_person
    from gcrm.tools.db_people_interactions import get_person_interactions
    from gcrm.tools.llm import get_llm

    person = get_person(person_id)
    if person is None:
        raise LookupError("Person not found")

    template = CURIOSITY_TEMPLATES.get(language, CURIOSITY_TEMPLATES["en"])
    organization = get_organization(person["contact_id"]) if person.get("contact_id") else None
    recent_notes = get_person_interactions(person_id)[:5]

    try:
        system, user = draft_curiosity_observation_prompt(person, organization, recent_notes, language)
        resp = get_llm(SMART_LLM).invoke([SystemMessage(content=system), HumanMessage(content=user)])
        observation = parse_llm_json(_content_to_text(resp.content))["observation"]
    except Exception:
        # The detail stays in the server log; the web client gets a fixed
        # string. str(error) here reached the app verbatim, and an upstream
        # SDK error can carry request URLs, model wiring, even key fragments.
        logger.exception("curiosity email draft failed for person_id=%d", person_id)
        return {"error": DRAFT_FAILED}

    first_name = (person.get("name") or "").split(" ")[0] or person.get("name", "")
    field = _field_label(person, organization, template)

    subject = template["subject"].format(field=field)
    body = "\n\n".join([
        template["greeting"].format(first_name=first_name),
        template["opening"],
        observation.strip(),
        template["ask"].format(field=field),
        template["closing"],
        template["signoff"],
    ])
    return {"subject": subject, "body": body}
