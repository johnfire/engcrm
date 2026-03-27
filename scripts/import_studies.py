"""
Import venue contacts from existing marketing study markdown files.

Reads each city's markdown file, uses the LLM to extract structured venue
records, and saves them to the database as status=candidate for the scout
agent to score.

Usage:
    uv run python scripts/import_studies.py

Safe to run multiple times — save_contact deduplicates by name+city.
"""
import json
import logging
import pathlib
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# City markdown files to import
STUDY_FILES = [
    pathlib.Path.home() / "ai-workzone/art-marketing-by-city/Ammersee-marketing-study/ammersee_venues_en.md",
    pathlib.Path.home() / "ai-workzone/art-marketing-by-city/Augsburg-markenting-study/augsburg_venues_en.md",
    pathlib.Path.home() / "ai-workzone/art-marketing-by-city/ingolstadt-marketing-study/ingolstadt_venues_en.md",
    pathlib.Path.home() / "ai-workzone/art-marketing-by-city/lindau-bergrenz-marketing study/lindau_bregenz_venues_en.md",
    pathlib.Path.home() / "ai-workzone/art-marketing-by-city/Nuremberg-marketing-study/nuernberg_venues_en.md",
    pathlib.Path.home() / "ai-workzone/art-marketing-by-city/Rosenheim-marketing-study/rosenheim_venues_en.md",
    pathlib.Path.home() / "ai-workzone/art-marketing-by-city/Starnbergersee-marketing study/starnberger_see_venues_en.md",
]

EXTRACT_PROMPT = """You are extracting venue records from an art marketing research document.

Extract every distinct venue, organisation, gallery, hotel, restaurant, café, museum,
or cultural institution mentioned. Include everything — let a scoring agent decide later
what is worth pursuing.

For each venue return a JSON object in a JSON array with these fields:
- name: venue name (string, required)
- city: city or town where it is located (string, required)
- country: "DE" for Germany, "AT" for Austria (string, default "DE")
- email: contact email if mentioned (string or null)
- phone: phone number if mentioned (string or null)
- website: website URL if mentioned (string or null)
- contact_person: named contact person if mentioned (string or null)
- type: best match from — gallery, restaurant, hotel, cafe, museum, office, coworking, bar, other (string)
- notes: star rating if shown (★★★/★★/★) plus one sentence summary of why this is relevant (string)

Rules:
- Include every unique venue even if contact details are missing
- Do not invent data — use null if a field is not in the document
- Return ONLY the JSON array, no preamble or explanation

Document:
{document}
"""


def _parse_json(text: str):
    """Strip markdown code fences then parse JSON."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    return json.loads(text)


def extract_venues(llm, markdown_text: str, filepath: str) -> list[dict]:
    from langchain_core.messages import HumanMessage

    prompt = EXTRACT_PROMPT.format(document=markdown_text)
    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        venues = _parse_json(response.content)
        if not isinstance(venues, list):
            logger.warning("%s: LLM returned non-list, got %s", filepath, type(venues))
            return []
        return venues
    except Exception as e:
        logger.error("%s: extraction failed — %s", filepath, e)
        return []


def import_file(llm, filepath: pathlib.Path, save_contact) -> tuple[int, int]:
    """Returns (saved, skipped) counts."""
    if not filepath.exists():
        logger.warning("File not found: %s", filepath)
        return 0, 0

    logger.info("Reading %s", filepath.name)
    markdown_text = filepath.read_text(encoding="utf-8")

    venues = extract_venues(llm, markdown_text, str(filepath))
    logger.info("%s: extracted %d venues", filepath.name, len(venues))

    saved = 0
    skipped = 0
    for v in venues:
        name = (v.get("name") or "").strip()
        city = (v.get("city") or "").strip()
        if not name or not city:
            skipped += 1
            continue

        notes_parts = []
        if v.get("contact_person"):
            notes_parts.append(f"Contact: {v['contact_person']}")
        if v.get("notes"):
            notes_parts.append(v["notes"])
        notes = " | ".join(notes_parts)

        contact_id = save_contact(
            name=name,
            city=city,
            country=v.get("country") or "DE",
            type=v.get("type") or "",
            website=v.get("website") or "",
            email=v.get("email") or "",
            phone=v.get("phone") or "",
            notes=notes,
        )
        if contact_id:
            saved += 1
        else:
            skipped += 1

    return saved, skipped


def main():
    from gcrm.tools.db import save_contact
    from gcrm.tools.llm import get_llm

    llm = get_llm("deepseek-chat")

    total_saved = 0
    total_skipped = 0

    for filepath in STUDY_FILES:
        saved, skipped = import_file(llm, filepath, save_contact)
        total_saved += saved
        total_skipped += skipped
        logger.info("%s: %d saved, %d skipped", filepath.name, saved, skipped)

    print(f"\nImport complete: {total_saved} contacts saved, {total_skipped} skipped")
    print("Run the supervisor (uv run python -m src.supervisor.run) to score and process them.")


if __name__ == "__main__":
    # Add project root to path so src.* imports work
    sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
    main()
