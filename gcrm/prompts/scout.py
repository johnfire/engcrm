import json

from gcrm.vertical import ANTI_SIGNALS, FIT_SIGNALS


def score_organization_prompt(mission, organization: dict, city_context: dict | None = None) -> tuple[str, str]:
    """
    Evaluate a contact for mission fit based on website content and notes.
    Reads FIT_SIGNALS and ANTI_SIGNALS from vertical.py.
    """
    city_context_str = ""
    if city_context and city_context.get("market_character", "unknown") != "unknown":
        char = city_context["market_character"]
        notes = city_context.get("market_notes", "")
        city_context_str = f"\nCity market context ({char}): {notes}\n"

    positive_signals = "\n".join(f"- {signal}" for signal in FIT_SIGNALS)
    negative_signals = "\n".join(f"- {signal}" for signal in ANTI_SIGNALS)

    system = (
        f"You are researching potential contacts on behalf of {mission.identity}.\n"
        f"Mission: {mission.goal}\n"
        f"{city_context_str}\n"
        f"Your task: read this contact's website content and notes carefully and determine "
        f"whether they are a realistic outreach target.\n\n"
        f"Positive signals (indicates a good fit):\n{positive_signals}\n\n"
        f"Negative signals (indicates a poor fit):\n{negative_signals}\n\n"
        f"If the website is thin or no content was fetched, use whatever is in "
        f"the notes field and answer 'unsure'.\n\n"
        f"Be specific in your reasoning — quote language from the website or notes, "
        f"name specific details that tipped the decision."
    )
    organization_json = json.dumps(organization, ensure_ascii=False, indent=2)
    user = (
        f"Evaluate this contact:\n\n"
        f"{organization_json}\n\n"
        f"Return a JSON object with EXACTLY these keys:\n"
        f"- outcome: one of 'fit' | 'unsure' | 'no_fit'\n"
        f"  fit = realistic outreach target\n"
        f"  unsure = unclear, mixed signals, or website too thin to judge\n"
        f"  no_fit = clearly not a fit based on negative signals\n"
        f"- reasoning: 3-5 sentences. Be specific.\n\n"
        f"Return ONLY the JSON object, no other text."
    )
    return system, user
