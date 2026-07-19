"""
EngCRM — Post-Meeting Debrief Interview

Interviews you after a face-to-face meeting or discovery call and saves answers
directly to the database.

Usage:
    uv run engcrm-interview
    # or:
    uv run python -m engcrm_interview_agent.interview

Voice input tip (Ubuntu/Wayland):
    Install nerd-dictation: https://github.com/ideasman42/nerd-dictation
    Works system-wide — speak and it types into any terminal.
"""
import sys
from datetime import date

from engcrm_interview_agent.db import db

# Import vertical config for customisable options.
# Falls back to eng-specific defaults if vertical.py is not on the path.
try:
    import os as _os
    import sys as _sys
    _sys.path.insert(0, _os.path.expanduser("~/programming/eng-crm"))
    from gcrm.vertical import INTERVIEW_APP_NAME, INTERVIEW_MATERIALS_OPTIONS
except (ImportError, AttributeError):
    INTERVIEW_APP_NAME = "EngCRM"
    INTERVIEW_MATERIALS_OPTIONS = [
        "business card",
        "one-pager",
        "demo link",
        "proposal",
        "case study",
        "Förderung info sheet",
        "nothing",
    ]


# ── UI helpers ────────────────────────────────────────────────────────────────

def hr():
    print("\n" + "─" * 50)


def ask(prompt, default=None):
    suffix = f" [{default}]" if default else " (Enter to skip)"
    val = input(f"  {prompt}{suffix}: ").strip()
    return val if val else default


def menu(prompt, options, allow_skip=True):
    print(f"\n  {prompt}")
    for i, opt in enumerate(options, 1):
        print(f"    {i}. {opt}")
    if allow_skip:
        print("    0. skip")
    while True:
        raw = input("  Choice: ").strip()
        if allow_skip and raw in ("", "0"):
            return None
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(options):
                return options[idx]
        except ValueError:
            pass
        print("  Invalid — try again.")


def multi_menu(prompt, options):
    print(f"\n  {prompt}")
    for i, opt in enumerate(options, 1):
        print(f"    {i}. {opt}")
    print("    0. skip / none")
    while True:
        raw = input("  Choices (e.g. 1,3): ").strip()
        if not raw or raw == "0":
            return []
        try:
            idxs = [int(x.strip()) - 1 for x in raw.split(",")]
            if all(0 <= i < len(options) for i in idxs):
                return [options[i] for i in idxs]
        except ValueError:
            pass
        print("  Invalid — try again.")


# ── database ──────────────────────────────────────────────────────────────────

def search_contacts(query: str) -> list[dict]:
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, name, city, country, status, type, first_impression
            FROM contacts
            WHERE deleted_at IS NULL
              AND (lower(name) LIKE %s OR lower(city) LIKE %s)
            ORDER BY lower(name)
            LIMIT 15
            """,
            (f"%{query.lower()}%", f"%{query.lower()}%"),
        )
        return [dict(r) for r in cur.fetchall()]


def save_updates(contact_id: int, updates: dict):
    if not updates:
        return
    fields = ", ".join(f"{k} = %s" for k in updates)
    values = list(updates.values()) + [contact_id]
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            f"UPDATE contacts SET {fields}, updated_at = NOW() WHERE id = %s",
            values,
        )


def append_notes(contact_id: int, new_text: str):
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT notes FROM contacts WHERE id = %s", (contact_id,))
        row = cur.fetchone()
        existing = (row["notes"] or "").strip()
        today = date.today().isoformat()
        combined = f"{existing}\n\n[{today}] {new_text}".strip() if existing else f"[{today}] {new_text}"
        cur.execute(
            "UPDATE contacts SET notes = %s, updated_at = NOW() WHERE id = %s",
            (combined, contact_id),
        )


# ── contact picker ────────────────────────────────────────────────────────────

def pick_contact() -> dict | None:
    while True:
        query = input("\n  Search company name or city (or Enter to finish): ").strip()
        if not query:
            return None

        results = search_contacts(query)
        if not results:
            print("  No matches found. Try again.")
            continue

        print(f"\n  Found {len(results)} match(es):")
        for i, c in enumerate(results, 1):
            loc = f"{c['city']}, {c['country']}" if c.get("country") else c.get("city", "")
            print(f"    {i}. {c['name']}  [{loc}]  {c['status']}")
        print("    0. search again")

        raw = input("  Select: ").strip()
        if raw == "0" or not raw:
            continue
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(results):
                return results[idx]
        except ValueError:
            pass
        print("  Invalid — try again.")


# ── interview ─────────────────────────────────────────────────────────────────

VALID_STATUSES = [
    "candidate", "cold", "contacted", "networking_visit",
    "meeting", "proposal", "accepted", "on_hold", "dropped", "do_not_contact",
]


def interview_contact(contact: dict) -> None:
    hr()
    loc = contact.get("city", "")
    print(f"\n  Company : {contact['name']}  {loc}  [{contact['status']}]")
    if contact.get("first_impression"):
        print(f"  First impression on record: {contact['first_impression']}")

    updates = {}
    today_str = date.today().isoformat()

    # Date of meeting
    visited = ask("Date of meeting", default=today_str)
    if visited:
        updates["last_visited_at"] = visited

    # Status update
    current = contact.get("status", "")
    new_status = menu(f"Update status? (current: {current})", VALID_STATUSES)
    if new_status:
        updates["status"] = new_status

    # Who did you meet
    dm = ask("Who did you meet? (name / role / title)")
    if dm:
        updates["decision_maker"] = dm

    # Impression / tone
    impression = menu("How did the meeting go?", ["warm", "neutral", "cold", "skeptical"])
    if impression:
        updates["last_impression"] = impression
        if not contact.get("first_impression"):
            updates["first_impression"] = impression

    # Materials / collateral shared
    materials = multi_menu("What did you share or leave?", INTERVIEW_MATERIALS_OPTIONS)
    if materials:
        updates["materials_left"] = ", ".join(materials)

    # Follow-up commitments
    followup = ask("What did you commit to? (e.g. 'send proposal by Friday', 'demo next week')")
    if followup:
        updates["followup_promised"] = followup

    # Preferred contact method going forward
    pref = menu(
        "Best way to reach them going forward?",
        ["email", "phone", "LinkedIn", "in person", "via assistant"],
    )
    if pref:
        updates["preferred_contact_method"] = pref

    # Contact details gathered
    got_email = ask("Did you get a direct email address?")
    if got_email:
        updates["email"] = got_email

    got_phone = ask("Did you get a direct phone number?")
    if got_phone:
        updates["phone"] = got_phone

    # Office / logistics notes
    access = ask("Office / logistics notes? (location, parking, reception process…)")
    if access:
        updates["access_notes"] = access

    # Company / team observations
    space = ask("Company notes? (team size, tech stack visible, culture vibe…)")
    if space:
        updates["space_notes"] = space

    # Budget / commercial signals
    price = ask("Budget / commercial signals? (mentioned Förderung, price sensitivity, decision timeline…)")
    if price:
        updates["price_sensitivity"] = price

    # Best time to follow up
    best_time = ask("Best time / channel for follow-up?")
    if best_time:
        updates["best_visit_time"] = best_time

    # Free notes
    free_notes = ask("Anything else to note?")

    # Persist
    save_updates(contact["id"], updates)
    if free_notes:
        append_notes(contact["id"], free_notes)

    saved_fields = list(updates.keys()) + (["notes"] if free_notes else [])
    print(f"\n  Saved: {', '.join(saved_fields)}")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"\n  {INTERVIEW_APP_NAME} — Post-Meeting Debrief")
    print("  Search for each company you met today. Empty search = done.\n")

    count = 0
    while True:
        contact = pick_contact()
        if contact is None:
            break
        interview_contact(contact)
        count += 1

    hr()
    if count == 0:
        print("\n  No contacts logged. Goodbye.\n")
    else:
        print(f"\n  Done — {count} contact(s) updated. Goodbye.\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  Interrupted. Any saves already made are kept.\n")
        sys.exit(0)
