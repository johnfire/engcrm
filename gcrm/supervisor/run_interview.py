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

from gcrm.activity_types import IMPRESSIONS, parse_occurred_on
from gcrm.db.connection import db
from gcrm.organization_state import PIPELINE_STAGES, STATUSES
from gcrm.tools.db_deals import organization_deal_join, set_organization_deal
from gcrm.tools.db_interactions import log_meeting_note
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

def search_organizations(query: str) -> list[dict]:
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT c.id, c.name, c.city, c.country, d.pipeline_stage, d.status, c.type
            FROM contacts c {organization_deal_join("c", "d")}
            WHERE c.deleted_at IS NULL
              AND (lower(c.name) LIKE %s OR lower(c.city) LIKE %s)
            ORDER BY lower(c.name)
            LIMIT 15
            """,
            (f"%{query.lower()}%", f"%{query.lower()}%"),
        )
        return [dict(row) for row in cur.fetchall()]


def pick_organization() -> dict | None:
    """Search for a contact and let the user select one. Returns contact dict or None."""
    while True:
        query = input("\n  Search business name or city (or Enter to finish): ").strip()
        if not query:
            return None

        results = search_organizations(query)
        if not results:
            print("  No matches. Try again or Enter to finish.")
            continue

        print(f"\n  Found {len(results)} match(es):")
        for index, organization in enumerate(results, 1):
            location = f"{organization['city']}, {organization['country']}" if organization.get("country") else organization.get("city", "")
            print(f"    {index}. {organization['name']}  [{location}]  {organization['status']}")
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
    """Write the debrief: stage and status to the Consulting deal, the rest to the organization."""
    if not updates:
        return
    columns = {k: v for k, v in updates.items() if k not in ("pipeline_stage", "status")}
    fields = "".join(f"{column} = %s, " for column in columns)
    values = list(columns.values()) + [contact_id]
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            f"UPDATE contacts SET {fields}updated_at = NOW() WHERE id = %s",
            values,
        )
        if "pipeline_stage" in updates or "status" in updates:
            set_organization_deal(
                cur, contact_id, stage=updates.get("pipeline_stage"), status=updates.get("status"),
            )


# ── interview ─────────────────────────────────────────────────────────────────

def _prompt_visit_outcome(organization: dict) -> tuple[dict, dict]:
    """Ask what happened on the visit. Returns (organization field updates, the
    visit itself): stage, status and who was seen change the organization; the
    date, impression, materials and any promise are logged as one in-person
    activity, the same record the Log activity form writes."""
    updates, visit = {}, {}

    visited = ask("Date of visit", default=date.today().isoformat())
    if visited:
        visit["occurred_on"] = visited

    # Where the relationship stands, and what is going on right now.
    current_stage = organization.get("pipeline_stage", "")
    new_stage = menu(
        f"Move pipeline stage? (current: {current_stage})",
        list(PIPELINE_STAGES),
    )
    if new_stage:
        updates["pipeline_stage"] = new_stage

    current_status = organization.get("status", "")
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

    impression = menu("How did it go? (impression)", list(IMPRESSIONS))
    if impression:
        visit["impression"] = impression

    materials = multi_menu(
        "What did you leave behind?",
        INTERVIEW_MATERIALS_OPTIONS,
    )
    if materials:
        visit["materials_left"] = ", ".join(materials)

    followup = ask("Did you promise anything? (e.g. 'send proposal', 'visit in May')")
    if followup:
        visit["follow_up_text"] = followup

    return updates, visit


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


def _prompt_visit_updates(organization: dict) -> tuple[dict, dict, str | None]:
    """Run the full debrief Q&A for one contact. Returns (field updates, the
    visit to log, notes)."""
    updates, visit = _prompt_visit_outcome(organization)
    updates.update(_prompt_site_notes())

    # Free notes become what the logged visit says happened.
    free_notes = ask("Anything else to note?")

    return updates, visit, free_notes


def log_visit(contact_id: int, visit: dict, free_notes: str | None) -> None:
    """Record the visit as an in-person activity on its day."""
    log_meeting_note(
        contact_id, "in_person", free_notes or "Visit (debrief)",
        follow_up_text=visit.get("follow_up_text"),
        occurred_on=parse_occurred_on(visit.get("occurred_on")),
        impression=visit.get("impression"),
        materials_left=visit.get("materials_left"),
    )


def interview_organization(organization: dict) -> None:
    hr()
    loc = f"{organization['city']}" if organization.get("city") else ""
    print(f"\n  Business: {organization['name']}  {loc}  [{organization['status']}]")

    updates, visit, free_notes = _prompt_visit_updates(organization)

    save_updates(organization["id"], updates)
    log_visit(organization["id"], visit, free_notes)

    changed = list(updates.keys()) + ["visit logged"]
    print(f"\n  Saved: {', '.join(changed)}")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"\n  {INTERVIEW_APP_NAME} — Post-Visit Debrief")
    print("  Enter each business you visited. Empty search = done.\n")
    print("  Tip: use nerd-dictation for voice input on Ubuntu.")
    print("  https://github.com/ideasman42/nerd-dictation")

    count = 0
    while True:
        organization = pick_organization()
        if organization is None:
            break
        interview_organization(organization)
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
