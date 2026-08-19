"""
Import the Bavaria startup & innovation ecosystem directory into the CRM.

Organisations become `contacts` (status candidate, typed so they stay separable
from the art-marketing pipeline that shares the table); the named transfer-office
and network contacts become `people` linked to their institution.

Two phases, each preview-by-default:

    # 1. See what would be created/updated. Touches nothing.
    uv run python scripts/import_bavaria_directory.py

    # 2. Import organisations and their named contacts.
    uv run python scripts/import_bavaria_directory.py --apply

    # 3. Look up a website for the rows that still lack one (DuckDuckGo, no LLM).
    uv run python scripts/import_bavaria_directory.py --websites
    uv run python scripts/import_bavaria_directory.py --websites --apply

Re-running is safe: organisations already present are never duplicated, and an
existing row is only ever filled in where a field is empty — nothing the CRM
already holds is overwritten.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from data.bavaria_directory import SOURCE, all_rows  # noqa: E402

from gcrm.db.connection import db  # noqa: E402
from gcrm.tools.db_audit import log_audit  # noqa: E402
from gcrm.tools.db_contacts import save_contact  # noqa: E402
from gcrm.tools.db_people import save_person  # noqa: E402

STATUS = "candidate"


def normalise_website(raw: str) -> str:
    """The directory lists bare domains ("zollhof.de"); the CRM stores URLs."""
    raw = (raw or "").strip()
    if not raw:
        return ""
    return raw if raw.startswith(("http://", "https://")) else f"https://{raw}"


def find_contact(name: str, city: str) -> dict | None:
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, name, city, website, email, phone, address, type, source FROM contacts "
            "WHERE lower(name) = lower(%s) AND lower(city) = lower(%s) AND deleted_at IS NULL",
            (name, city),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def fill_blanks(contact_id: int, row: dict, kind: str, existing: dict) -> list[str]:
    """Fill only the fields the existing contact is missing. Returns field names."""
    wanted = {
        "website": normalise_website(row.get("website", "")),
        "email": row.get("email", ""),
        "phone": row.get("phone", ""),
        "address": row.get("address", ""),
        "type": kind,
    }
    updates = {
        column: value for column, value in wanted.items()
        if value and not (existing.get(column) or "").strip()
    }
    if not updates:
        return []
    assignments = ", ".join(f"{column} = %s" for column in updates)
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            f"UPDATE contacts SET {assignments}, updated_at = NOW() WHERE id = %s",
            list(updates.values()) + [contact_id],
        )
    log_audit(None, None, "contact.directory_filled", f"contact:{contact_id}", "updated")
    return sorted(updates)


def stamp_extras(contact_id: int, row: dict, source: str) -> None:
    """save_contact() has no source/address parameters; set them after insert."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE contacts SET source = %s, address = COALESCE(%s, address), "
            "updated_at = NOW() WHERE id = %s",
            (source, row.get("address") or None, contact_id),
        )


def import_orgs(apply: bool) -> None:
    created = linked = filled = unchanged = 0
    people_made = 0
    for kind, row in all_rows():
        existing = find_contact(row["name"], row["city"])
        if existing:
            changed = fill_blanks(existing["id"], row, kind, existing) if apply else []
            if apply and changed:
                filled += 1
                print(f"  fill   [{existing['id']:>4}] {row['name'][:44]:<44} <- {', '.join(changed)}")
            elif apply:
                unchanged += 1
            else:
                linked += 1
                print(f"  exists         {row['name'][:44]:<44} ({row['city']})")
            contact_id = existing["id"]
        elif not apply:
            created += 1
            site = normalise_website(row.get("website", "")) or "-- no website --"
            print(f"  new    {kind:<20} {row['name'][:40]:<40} {site}")
            contact_id = 0
        else:
            contact_id = save_contact(
                name=row["name"], city=row["city"], country="DE", type=kind,
                website=normalise_website(row.get("website", "")),
                email=row.get("email", ""), phone=row.get("phone", ""),
                notes=row.get("notes", ""), status=STATUS,
            )
            if contact_id:
                stamp_extras(contact_id, row, SOURCE)
                created += 1
                print(f"  new    [{contact_id:>4}] {row['name'][:44]:<44}")
            else:
                # Deduped on email against a differently-named row.
                unchanged += 1

        person = row.get("person")
        if person and apply and contact_id:
            save_person(
                name=person["name"], title=person.get("title", "Technologietransfer"),
                email=person.get("email", ""), city=row["city"], country="DE",
                contact_id=contact_id, source=SOURCE,
            )
            people_made += 1

    print()
    if apply:
        print(f"organisations: {created} created, {filled} filled in, {unchanged} already complete")
        print(f"people:        {people_made} linked to their institution")
    else:
        print(f"DRY RUN: {created} would be created, {linked} already exist.")
        print("Add --apply to write.")


def _domain(url: str) -> str:
    return url.split("//")[-1].split("/")[0].lower().removeprefix("www.")


def _tokens(text: str) -> set[str]:
    drop = {"der", "die", "das", "und", "für", "hochschule", "universität", "university",
            "gmbh", "th", "the", "of", "centre", "center", "tech"}
    words = "".join(c if c.isalnum() else " " for c in text.lower()).split()
    return {w for w in words if len(w) > 2 and w not in drop}


def _verify(domain: str, org_name: str) -> tuple[bool, str]:
    """Fetch the candidate site and check it actually belongs to the org.

    Returns (ok, evidence). A domain is only accepted when the page really loads
    and its text carries distinctive words from the organisation's name, so a
    parked or unrelated site cannot slip through as a "found" website.
    """
    from gcrm.tools.search import fetch_page

    url = f"https://{domain}"
    text = fetch_page(url, max_chars=2500)
    if not text.strip():
        return False, "no page content"
    overlap = _tokens(org_name) & _tokens(text)
    if not overlap:
        return False, "page does not mention the organisation"
    return True, "matched: " + ", ".join(sorted(overlap)[:3])


def _email_domain_candidate(contact_id: int, org_email: str | None) -> str:
    """The directory records a contact address for most rows, and an institution's
    own address carries its domain — a far better signal than a web search."""
    if org_email and "@" in org_email:
        return org_email.split("@")[-1].strip().lower()
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT email FROM people WHERE contact_id = %s AND email IS NOT NULL "
            "ORDER BY id LIMIT 1",
            (contact_id,),
        )
        row = cur.fetchone()
    if row and "@" in (row["email"] or ""):
        return row["email"].split("@")[-1].strip().lower()
    return ""


def find_websites(apply: bool) -> None:
    """Fill in a website for every imported organisation that still lacks one.

    The only automatic source is the domain of a contact address the directory
    already recorded — an institution's own address is strong provenance, and the
    candidate is still fetched and checked against the organisation name before
    it is written.

    A general web-search fallback was removed deliberately: gcrm.tools.search
    currently returns unrelated results, and matching on a single generic token
    was enough to accept a perfume retailer as "Areal Digital". Rows with no
    contact address are reported for a human to resolve instead of guessed at.
    """
    from gcrm.tools.db_contacts import update_contact_details

    with db() as conn:
        cur = conn.cursor()
        # startup_hub rows are places, not organisations — searching "Munich"
        # returns tourism portals, not something that belongs in this column.
        cur.execute(
            "SELECT id, name, city, email FROM contacts WHERE source = %s "
            "AND (website IS NULL OR website = '') AND type <> 'startup_hub' "
            "AND deleted_at IS NULL ORDER BY id",
            (SOURCE,),
        )
        targets = [dict(r) for r in cur.fetchall()]

    if not targets:
        print("Every imported organisation already has a website.")
        return

    print(f"{len(targets)} organisation(s) without a website:\n")
    found = unresolved = 0
    for target in targets:
        domain = _email_domain_candidate(target["id"], target.get("email"))
        accepted = None
        if domain:
            ok, evidence = _verify(domain, target["name"])
            if ok:
                accepted = (domain, "contact email domain", evidence)

        if not accepted:
            unresolved += 1
            print(f"  --     [{target['id']:>4}] {target['name'][:42]:<42} no verified site")
            continue

        domain, how, evidence = accepted
        found += 1
        if apply:
            update_contact_details(target["id"], website=f"https://{domain}")
            log_audit(None, None, "contact.website_found", f"contact:{target['id']}", "updated")
        print(f"  ok     [{target['id']:>4}] {target['name'][:42]:<42} https://{domain}")
        print(f"         via {how}; {evidence}")

    print(f"\n{found} verified, {unresolved} still without a website.")
    if not apply:
        print("DRY RUN — add --apply to write the verified ones.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="write (default is preview)")
    parser.add_argument("--websites", action="store_true",
                        help="look up websites for imported rows that lack one")
    args = parser.parse_args()

    if args.websites:
        find_websites(args.apply)
    else:
        import_orgs(args.apply)
    return 0


if __name__ == "__main__":
    sys.exit(main())
