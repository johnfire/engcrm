"""
Import contacts from the 'contacts  leads' sheet of art-marketing.xlsx.

Rules:
- Contacts with count numbers (col C) have been actively contacted → status=contacted
- Contacts with '*' in col K but no count → suspect / ready (good targets, not yet contacted)
- Contacts with no count and no '*' → candidate / none
- Contacts with rejection notes ('def no', 'no interest', etc.) → not_in_pipeline / dropped
- Contacts with 'ON HOLD' → prospect / on_hold
- City inferred from section headers in col A/B
- Type inferred from sub-section headers (Galleries, Cafes, etc.)
- Questionable rows get [NEEDS REVIEW] prepended to their notes

Run with:
    uv run python scripts/import_contacts_leads.py --dry-run   # preview only
    uv run python scripts/import_contacts_leads.py             # actually import
"""
import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import openpyxl

from gcrm.db.connection import db

WORKBOOK_PATH = Path(__file__).parent.parent / "art-marketing.xlsx"
SHEET_NAME = "contacts  leads"

# Status mapping from notes in col I
REJECTION_PATTERNS = ["def no", "no interest", "no intrest", "not interested", "rejected", "negative"]
HOLD_PATTERNS = ["on hold", "hold"]
NOT_NOW_PATTERNS = ["not now", "try in april", "try in may", "wait a year"]

# Sub-section type mapping
TYPE_MAP = {
    "gallerie": "gallery",
    "galerie": "gallery",
    "gallery": "gallery",
    "galleries": "gallery",
    "cafe": "cafe",
    "cafes": "cafe",
    "restaurant": "cafe",
    "cafes restaurants": "cafe",
    "interior": "interior_designer",
    "interior designer": "interior_designer",
    "interior designers": "interior_designer",
    "co working": "coworking",
    "coworking": "coworking",
    "hotel": "hotel",
    "corporation": "corporate",
    "corporations": "corporate",
    "office": "corporate",
    "art consultant": "interior_designer",
    "other": "other",
    "others": "other",
    "people": "person",
    "person": "person",
    "internet": "online",
    "online": "online",
    "on line": "online",
}

# City normalization
CITY_MAP = {
    "aux": "Augsburg",
    "auxburg": "Augsburg",
    "augsburg": "Augsburg",
    "landsberg": "Landsberg am Lech",
    "munich": "Munich",
    "münchen": "Munich",
    "innsbruck": "Innsbruck",
    "nuremberg": "Nuremberg",
    "nürnberg": "Nuremberg",
    "wurzburg": "Würzburg",
    "würzburg": "Würzburg",
    "rothenburg ob": "Rothenburg ob der Tauber",
    "friedberg": "Friedberg",
    "dachau": "Dachau",
}

# These look like names but are actually section headers or notes — skip them
SKIP_PATTERNS = [
    r"^https?://",
    r"^www\.",
    r"^=",                          # formula strings
    r"^in process",
    r"^galleries:?$",
    r"^galerie[s]?:?$",
    r"^cafes?\s*(restaurants?)?:?$",
    r"^restaurants?:?$",
    r"^interior designers?:?$",
    r"^co.?working spaces?:?$",
    r"^corporations?\s*(and offices?)?",
    r"^others?:?$",
    r"^people:?$",
    r"^internet:?$",
    r"^online:?$",
    r"^on line:?$",
    r"^need ",
    r"^go look",
    r"^done at least",
    r"^fridays",
    r"^lange nacht",
    r"^expect ",
    r"^total ",
    r"^name$",
    r"^sub city$",
    r"^city$",
    r"^maybe\s*:",
    r"^zeitgeist",                  # summary note rows at the top
    r"^in process,? or started",
    r"^regardez vintage,",          # summary note, not a contact
    r"^something on bozner",        # reminder note
]


def normalize_city(raw: str) -> str:
    if not raw:
        return ""
    return CITY_MAP.get(raw.strip().lower(), raw.strip().title())


def infer_type(section_header: str) -> str:
    if not section_header:
        return ""
    lower = section_header.strip().lower().rstrip("s:").strip()
    for key, val in TYPE_MAP.items():
        if key in lower:
            return val
    return ""


def parse_status(count, reply_notes: str, poss_target: str) -> tuple[str, str, bool]:
    """
    Returns (pipeline_stage, status, needs_review).
    """
    notes_lower = (reply_notes or "").strip().lower()

    # Hard rejections
    if any(p in notes_lower for p in REJECTION_PATTERNS):
        return "not_in_pipeline", "dropped", False

    # On hold
    if any(p in notes_lower for p in HOLD_PATTERNS):
        return "prospect", "on_hold", False

    # Active contact with count number
    if count and str(count).isdigit():
        # 'not now' after contact = ready to try again
        if any(p in notes_lower for p in NOT_NOW_PATTERNS):
            return "prospect", "on_hold", False
        return "prospect", "contacted", False

    # Possible target flag but not yet contacted
    if poss_target and str(poss_target).strip() in ("*", "?"):
        if poss_target.strip() == "?":
            return "candidate", "none", True  # uncertain
        return "suspect", "ready", False

    # Anything else with a contact date but no count
    return "candidate", "none", False


def should_skip(name: str) -> bool:
    if not name or not str(name).strip():
        return True
    name_str = str(name).strip()
    if len(name_str) < 2:
        return True
    for pattern in SKIP_PATTERNS:
        if re.match(pattern, name_str, re.IGNORECASE):
            return True
    # Very long entries are likely notes, not names
    if len(name_str) > 60:
        return True
    return False


def is_questionable(name: str, city: str, notes_raw: str) -> tuple[bool, list[str]]:
    reasons = []
    name_str = str(name or "").strip()
    # Partial address or description mixed in
    if any(c in name_str for c in [",", "•", "/"]) and len(name_str) > 30:
        reasons.append("name looks like a description")
    if not city:
        reasons.append("city unknown")
    if "?" in str(notes_raw or ""):
        reasons.append("uncertain notes")
    return bool(reasons), reasons


def extract_organizations(ws) -> list[dict]:
    organizations = []
    current_city = ""
    current_section = ""
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        col_a = row[0]   # section number
        col_b = row[1]   # city or notes
        col_c = row[2]   # count / sequence
        col_d = row[3]   # first contact date
        col_i = row[8]   # current reply / status
        col_k = row[10]  # poss target (*)
        col_m = row[12]  # best walk-in time
        col_n = row[13]  # name
        col_o = row[14]  # sub-city

        # Detect city section headers (col A has a number, col B has city name)
        if col_a is not None and isinstance(col_a, (int, float)) and col_b:
            city_raw = str(col_b).strip()
            if city_raw.lower() not in ("unlikely", "in person", "2 visits", "alt", "not now", "waiting", "internet"):
                current_city = normalize_city(city_raw)
                current_section = ""
                continue

        # Detect sub-section headers (col N has something like "Galleries:", "Cafes:")
        if col_n and not col_c and not col_d and not col_k:
            name_str = str(col_n).strip().lower().rstrip(": ").rstrip("s").strip()
            for key in TYPE_MAP:
                if key in name_str and len(str(col_n).strip()) < 50:
                    current_section = str(col_n).strip()
                    break

        # Also detect section from col B if it looks like a header
        if col_b and not col_n and str(col_b).strip().lower() in [k + "s" for k in TYPE_MAP] + list(TYPE_MAP.keys()):
            current_section = str(col_b).strip()

        # Skip if no name
        if not col_n:
            continue
        name = str(col_n).strip()
        if should_skip(name):
            continue

        # Clean name — strip trailing annotations after '--'
        name = re.sub(r'\s*--.*$', '', name).strip()
        # Strip trailing descriptive sentence (5+ words = likely a description appended)
        words = name.split()
        if len(words) > 4:
            name = ' '.join(words[:4])
        # Strip trailing period or comma
        name = name.rstrip('.,').strip()

        # City: prefer col O sub-city if it maps to a known city, else use current_city
        sub_city = str(col_o).strip() if col_o else ""
        city = normalize_city(sub_city) if sub_city and normalize_city(sub_city) != sub_city.title() else current_city
        if not city and sub_city:
            city = sub_city.title()

        # Type from current section
        organization_type = infer_type(current_section)

        # Status
        reply = str(col_i).strip() if col_i else ""
        poss_tgt = str(col_k).strip() if col_k else ""
        count_val = col_c
        pipeline_stage, status, review_from_status = parse_status(count_val, reply, poss_tgt)

        # First contact date
        first_contact = col_d if isinstance(col_d, datetime) else None

        # Best visit time
        visit_time = str(col_m).strip() if col_m else ""

        # Notes assembly
        notes_parts = []
        if col_b and str(col_b).strip().lower() not in ("in person", "unlikely", "2 visits", "alt", "not now", "waiting"):
            notes_parts.append(str(col_b).strip())
        if reply and reply.lower() not in ("none", "nothing", "yes", "no"):
            notes_parts.append(f"status note: {reply}")
        if first_contact:
            notes_parts.append(f"first contact: {first_contact.strftime('%Y-%m-%d')}")

        raw_notes = "; ".join(notes_parts)

        # Questionable check
        q_flag, q_reasons = is_questionable(name, city, reply)
        needs_review = review_from_status or q_flag

        final_notes = raw_notes
        if needs_review:
            reason_str = ", ".join(q_reasons) if q_reasons else "uncertain status"
            final_notes = f"[NEEDS REVIEW: {reason_str}] {raw_notes}".strip()

        organizations.append({
            "name": name,
            "city": city or "Unknown",
            "type": organization_type,
            "pipeline_stage": pipeline_stage,
            "status": status,
            "best_visit_time": visit_time,
            "notes": final_notes,
            "needs_review": needs_review,
            "source_row": i + 1,
        })

    return organizations


def import_organizations(organizations: list[dict], dry_run: bool = True):
    created = skipped_dup = needs_review = 0

    with db() as conn:
        cur = conn.cursor()
        for c in organizations:
            # Check duplicate by (name, city) case-insensitive
            cur.execute(
                "SELECT id FROM contacts WHERE lower(name) = lower(%s) AND lower(city) = lower(%s)",
                (c["name"], c["city"]),
            )
            existing = cur.fetchone()
            if existing:
                skipped_dup += 1
                continue

            if c["needs_review"]:
                needs_review += 1

            if not dry_run:
                cur.execute("""
                    INSERT INTO contacts
                        (name, city, country, type, pipeline_stage, status,
                         best_visit_time, notes)
                    VALUES (%s, %s, 'DE', %s, %s, %s, %s, %s)
                """, (
                    c["name"],
                    c["city"],
                    c["type"] or None,
                    c["pipeline_stage"],
                    c["status"],
                    c["best_visit_time"] or None,
                    c["notes"] or None,
                ))
            created += 1

    return created, skipped_dup, needs_review


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing to DB")
    args = parser.parse_args()

    print(f"Loading {WORKBOOK_PATH.name} ...")
    wb = openpyxl.load_workbook(WORKBOOK_PATH, read_only=True)
    ws = wb[SHEET_NAME]

    organizations = extract_organizations(ws)
    print(f"\nExtracted {len(organizations)} contacts from sheet\n")

    # Status breakdown
    from collections import Counter
    status_counts = Counter(f"{c['pipeline_stage']}/{c['status']}" for c in organizations)
    review_count = sum(1 for c in organizations if c["needs_review"])
    print("Status breakdown:")
    for s, n in sorted(status_counts.items()):
        print(f"  {s}: {n}")
    print(f"  [needs review]: {review_count}")

    if args.dry_run:
        print("\n--- DRY RUN: first 40 contacts that would be imported ---")
        for c in organizations[:40]:
            flag = " [REVIEW]" if c["needs_review"] else ""
            state = f"{c['pipeline_stage']}/{c['status']}"
            print(f"  row {c['source_row']:3d} | {state:24s} | {c['city']:20s} | {c['type']:18s} | {c['name']}{flag}")
        print("\nRe-run without --dry-run to actually import.")
        return

    created, skipped, nr = import_organizations(organizations, dry_run=False)
    print("\nImport complete:")
    print(f"  Created:       {created}")
    print(f"  Skipped (dup): {skipped}")
    print(f"  Needs review:  {nr}")


if __name__ == "__main__":
    main()
