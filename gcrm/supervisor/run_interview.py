"""
Post-visit debrief interview — ask questions after a recon trip and save answers to the DB.

Usage:
    uv run python -m gcrm.supervisor.run_interview

Voice input tip (Ubuntu):
    Install nerd-dictation for system-wide voice typing:
    https://github.com/ideasman42/nerd-dictation
    Works in any terminal — speak and it types for you.
"""
import sys
from datetime import date

from gcrm.contact_state import PIPELINE_STAGES, STATUSES
from gcrm.db.connection import db
from gcrm.vertical import INTERVIEW_APP_NAME, INTERVIEW_MATERIALS_OPTIONS

# ── helpers ──────────────────────────────────────────────────────────────────

def hr():
    print("\n" + "─" * 50)


def ask(prompt, default=None):
    """Free-text input. Enter skips (returns default)."""
    suffix = f" [{default}]" if default else " (Enter to skip)"
    val = input(f"  {prompt}{suffix}: ").strip()
    return val if val else default


def menu(prompt, options, allow_skip=True):
    """Numbered menu. Returns chosen value or None if skipped."""
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
    """Numbered menu where multiple choices can be selected (comma-separated)."""
    print(f"\n  {prompt}")
    for i, opt in enumerate(options, 1):
        print(f"    {i}. {opt}")
    print("    0. skip / none")
    while True:
        raw = input("  Choices (e.g. 1,3): ").strip()
        if not raw or raw == "0":
            return []
        try:
            indexes = [int(part.strip()) - 1 for part in raw.split(",")]
            if all(0 <= index < len(options) for index in indexes):
                return [options[index] for index in indexes]
        except ValueError:
            pass
        print("  Invalid — try again.")


# ── contact search ────────────────────────────────────────────────────────────

def search_contacts(query: str) -> list[dict]:
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, name, city, country, pipeline_stage, status, type
            FROM contacts
            WHERE deleted_at IS NULL
              AND (lower(name) LIKE %s OR lower(city) LIKE %s)
            ORDER BY lower(name)
            LIMIT 15
            """,
            (f"%{query.lower()}%", f"%{query.lower()}%"),
        )
        return [dict(row) for row in cur.fetchall()]


def pick_contact() -> dict | None:
    """Search for a contact and let the user select one. Returns contact dict or None."""
    while True:
        query = input("\n  Search business name or city (or Enter to finish): ").strip()
        if not query:
            return None

        results = search_contacts(query)
        if not results:
            print("  No matches. Try again or Enter to finish.")
            continue

        print(f"\n  Found {len(results)} match(es):")
        for index, contact in enumerate(results, 1):
            location = f"{contact['city']}, {contact['country']}" if contact.get("country") else contact.get("city", "")
            print(f"    {index}. {contact['name']}  [{location}]  {contact['status']}")
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


# ── save ──────────────────────────────────────────────────────────────────────

def save_updates(contact_id: int, updates: dict):
    if not updates:
        return
    fields = ", ".join(f"{column} = %s" for column in updates)
    values = list(updates.values()) + [contact_id]
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            f"UPDATE contacts SET {fields}, updated_at = NOW() WHERE id = %s",
            values,
        )


def append_notes(contact_id: int, new_text: str):
    """Append text to existing notes without overwriting."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT notes FROM contacts WHERE id = %s", (contact_id,))
        row = cur.fetchone()
        existing = (row["notes"] or "").strip()
        today = date.today().isoformat()
        combined = f"{existing}\n\n[{today}] {new_text}".strip() if existing else f"[{today}] {new_text}"
        cur.execute("UPDATE contacts SET notes = %s, updated_at = NOW() WHERE id = %s", (combined, contact_id))


# ── interview ─────────────────────────────────────────────────────────────────

def _resolve_impression(contact: dict) -> dict:
    """Ask how the visit went. Always records last_impression; sets first_impression
    only if the contact doesn't already have one. Returns fields to update."""
    impression = menu(
        "How did it go? (impression)",
        ["warm", "neutral", "cold", "skeptical"],
    )
    if not impression:
        return {}

    fields = {"last_impression": impression}
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT first_impression FROM contacts WHERE id = %s", (contact["id"],))
        row = cur.fetchone()
        if not row["first_impression"]:
            fields["first_impression"] = impression
    return fields


def _prompt_visit_outcome(contact: dict) -> dict:
    """Ask what happened on the visit — date, status, who was seen, impression,
    materials, and any promise. Returns fields to update."""
    updates = {}

    # Always mark last visited as today (can override)
    visited = ask("Date of visit", default=date.today().isoformat())
    if visited:
        updates["last_visited_at"] = visited

    # Where the relationship stands, and what is going on right now.
    current_stage = contact.get("pipeline_stage", "")
    new_stage = menu(
        f"Move pipeline stage? (current: {current_stage})",
        list(PIPELINE_STAGES),
    )
    if new_stage:
        updates["pipeline_stage"] = new_stage

    current_status = contact.get("status", "")
    new_status = menu(
        f"Update status? (current: {current_status})",
        list(STATUSES),
    )
    if new_status:
        updates["status"] = new_status

    # Decision maker
    dm = ask("Who did you speak to? (name/role)")
    if dm:
        updates["decision_maker"] = dm

    # Impressions (first_impression only set once)
    updates.update(_resolve_impression(contact))

    # Materials left
    materials = multi_menu(
        "What did you leave behind?",
        INTERVIEW_MATERIALS_OPTIONS,
    )
    if materials:
        updates["materials_left"] = ", ".join(materials)

    # Follow-up promised
    followup = ask("Did you promise anything? (e.g. 'send proposal', 'visit in May')")
    if followup:
        updates["followup_promised"] = followup

    return updates


def _prompt_site_notes() -> dict:
    """Ask how best to reach the contact and about site/commercial logistics.
    Returns fields to update."""
    updates = {}

    # Preferred contact method
    pref = menu(
        "Best way to reach them?",
        ["email", "phone", "drop in", "LinkedIn", "contact form"],
    )
    if pref:
        updates["preferred_contact_method"] = pref

    # Access / logistics
    access = ask("Access notes? (train, parking, hilly, hard to find…)")
    if access:
        updates["access_notes"] = access

    # Space
    space = ask("Site notes? (size, setup, vibe…)")
    if space:
        updates["space_notes"] = space

    # Price sensitivity
    price = ask("Price/commercial notes? (budget-conscious, wants fixed price…)")
    if price:
        updates["price_sensitivity"] = price

    return updates


def _prompt_visit_updates(contact: dict) -> tuple[dict, str | None]:
    """Run the full debrief Q&A for one contact. Returns (field updates, notes)."""
    updates = {}
    updates.update(_prompt_visit_outcome(contact))
    updates.update(_prompt_site_notes())

    # Free notes — appended, not overwritten
    free_notes = ask("Anything else to note?")

    return updates, free_notes


def interview_contact(contact: dict) -> None:
    hr()
    loc = f"{contact['city']}" if contact.get("city") else ""
    print(f"\n  Business: {contact['name']}  {loc}  [{contact['status']}]")

    updates, free_notes = _prompt_visit_updates(contact)

    save_updates(contact["id"], updates)
    if free_notes:
        append_notes(contact["id"], free_notes)

    changed = list(updates.keys()) + (["notes"] if free_notes else [])
    print(f"\n  Saved: {', '.join(changed)}")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"\n  {INTERVIEW_APP_NAME} — Post-Visit Debrief")
    print("  Enter each business you visited. Empty search = done.\n")
    print("  Tip: use nerd-dictation for voice input on Ubuntu.")
    print("  https://github.com/ideasman42/nerd-dictation")

    count = 0
    while True:
        contact = pick_contact()
        if contact is None:
            break
        interview_contact(contact)
        count += 1

    hr()
    if count == 0:
        print("\n  No businesses logged. Goodbye.\n")
    else:
        print(f"\n  Done. {count} business(es) updated. Goodbye.\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  Interrupted. Any saves already made are kept.\n")
        sys.exit(0)
