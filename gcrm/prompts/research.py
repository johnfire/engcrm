import json

from gcrm.vertical import BUYER_TYPES, NOT_A_BUYER_TYPES, SCAN_LEVELS, SIZE_RULE


def extract_organizations_prompt(
    mission,
    city: str,
    levels: list[int],
    raw_results: list[dict],
) -> tuple[str, str]:
    level_desc = "; ".join(
        SCAN_LEVELS[level]["label"] for level in levels if level in SCAN_LEVELS
    ) or "businesses"

    system = (
        f"You are extracting contact information for {mission.identity}.\n"
        f"Mission: {mission.goal}\n"
        f"You are scanning for: {level_desc}"
    )
    user = (
        f"From these search results for {level_desc} in {city}, extract every business found.\n\n"
        f"Fit criteria for later scoring — use this to write useful notes:\n{mission.fit_criteria}\n{SIZE_RULE}\n\n"
        f"For EVERY business found, extract:\n"
        f"- name (required)\n"
        f"- city (default: {city})\n"
        f"- country (2-letter ISO code)\n"
        f"- type: exactly one of {', '.join(BUYER_TYPES)}; or, for a shop or small service "
        f"that is not a company we sell to, exactly one of {', '.join(NOT_A_BUYER_TYPES)}\n"
        f"- address\n"
        f"- website\n"
        f"- email\n"
        f"- phone\n"
        f"- notes: 2-3 sentences:\n"
        f"  1. What the business is and makes or does\n"
        f"  2. Size signals: employee count, sites, production or fleet — or say size is unknown\n"
        f"  3. Fit assessment: strong fit / weak fit / unclear — be specific\n\n"
        f"Include ALL businesses from the results — do not filter here. The scout agent will score and drop bad fits.\n\n"
        f"Search results:\n{json.dumps(raw_results, ensure_ascii=False, indent=2)[:40000]}\n\n"
        f"Return a JSON array of objects. If nothing found at all, return [].\n"
        f"Return ONLY the JSON array, no other text."
    )
    return system, user
