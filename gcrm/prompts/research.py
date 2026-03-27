import json
from gcrm.vertical import SCAN_LEVELS, FIT_CRITERIA


def extract_contacts_prompt(
    mission,
    city: str,
    level: int,
    raw_results: list[dict],
) -> tuple[str, str]:
    level_info = SCAN_LEVELS.get(level, {})
    level_desc = level_info.get("label", "venues")

    system = (
        f"You are extracting contact information for {mission.identity}.\n"
        f"Mission: {mission.goal}\n"
        f"You are scanning for: {level_desc}"
    )
    user = (
        f"From these search results for {level_desc} in {city}, extract every venue found.\n\n"
        f"Fit criteria for later scoring — use this to write useful notes:\n{mission.fit_criteria}\n\n"
        f"For EVERY venue found, extract:\n"
        f"- name (required)\n"
        f"- city (default: {city})\n"
        f"- country (2-letter ISO code)\n"
        f"- type (one short lowercase label matching the venue type, e.g. gallery/restaurant/hotel/cafe/"
        f"interior_designer/coworking/corporate_office/concept_store/gift_shop/wellness/other)\n"
        f"- address\n"
        f"- website\n"
        f"- email\n"
        f"- phone\n"
        f"- notes: 2-3 sentences:\n"
        f"  1. What the venue is and does\n"
        f"  2. Signals about fit (openness to new suppliers/collaborators, relevant specialisation, etc.)\n"
        f"  3. Fit assessment: strong fit / weak fit / unclear — be specific\n\n"
        f"Include ALL venues from the results — do not filter here. The scout agent will score and drop bad fits.\n\n"
        f"Search results:\n{json.dumps(raw_results, ensure_ascii=False, indent=2)[:7000]}\n\n"
        f"Return a JSON array of objects. If nothing found at all, return [].\n"
        f"Return ONLY the JSON array, no other text."
    )
    return system, user
