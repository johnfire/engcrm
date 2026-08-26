"""Prompt for the one-off, non-sales "curiosity" first-contact email sent to
a specific person. Separate from gcrm/prompts/outreach.py's mission-driven
sales-pitch prompts — this is a different tone entirely (see
docs/plans/2026-08-26-person-curiosity-email-design.md)."""
import json

_LANGUAGE_NAMES = {"en": "English", "de": "German"}


def draft_curiosity_observation_prompt(
    person: dict,
    organization: dict | None,
    recent_notes: list[dict],
    language: str,
) -> tuple[str, str]:
    """Build the system/user prompt for the one LLM-authored slot in the
    curiosity email: a short, specific, genuine observation about this
    person or their business. Returns (system, user)."""
    language_name = _LANGUAGE_NAMES.get(language, "English")

    system = (
        "You write one or two sentences for a personal, non-sales first-contact "
        "email. The sentences must be specific and genuine — grounded in the "
        "notes provided, never invented, and never flattery. If the notes are "
        "thin or empty, write a brief, honest sentence based only on the "
        f"person's role or company. Write entirely in {language_name}."
    )

    person_section = json.dumps(
        {k: v for k, v in person.items() if k in ("name", "title", "city", "relationship", "notes")},
        ensure_ascii=False, indent=2,
    )

    if organization:
        org_section = "\n\nTheir company:\n" + json.dumps(
            {k: v for k, v in organization.items() if k in ("name", "type", "city", "notes", "website")},
            ensure_ascii=False, indent=2,
        )
    else:
        org_section = ""

    if recent_notes:
        lines = "\n".join(f"  {n.get('occurred_at', '?')} | {n.get('note', '')}" for n in recent_notes)
        notes_section = f"\n\nRecent interaction notes:\n{lines}"
    else:
        notes_section = ""

    user = (
        f"Person:\n{person_section}{org_section}{notes_section}\n\n"
        "Write one or two sentences that could open a personal email to this "
        "person — something specific enough that it could only be about them, "
        "not a generic compliment.\n\n"
        'Return JSON: {"observation": "..."}\n'
        "Return ONLY the JSON object, no other text."
    )
    return system, user
