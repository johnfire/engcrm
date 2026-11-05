"""Import a parsed lead list (gcrm.lead_list) into organizations and people — no LLM.

A company already in the CRM with the same name in the same town is matched and only its
blank fields are filled. (Not by website: one list can hold two entities that share a site,
e.g. MicroStep Europa and MicroStep CompetenceCenter Süd; a leftover duplicate is visible and
can be merged, a wrong merge is not.) A person already on the company (same name) or anywhere
with the same LinkedIn profile is reused. A dry run reports the same counts without writing.
Importing the same list again changes nothing.
"""
from datetime import date

from gcrm.db.connection import db
from gcrm.linkedin import normalize_linkedin_url
from gcrm.sources import LEAD_LIST
from gcrm.tools.db_agent_runs import finish_run, start_run
from gcrm.tools.db_audit import log_audit
from gcrm.tools.db_organizations import save_organization
from gcrm.tools.db_people import find_existing_person, save_person


def find_company(cur, name: str, town: str) -> int | None:
    cur.execute("SELECT id FROM contacts WHERE deleted_at IS NULL AND lower(name) = lower(%s) "
                "AND lower(city) = lower(%s) ORDER BY id LIMIT 1", (name, town))
    row = cur.fetchone()
    return row["id"] if row else None


def find_person(cur, person: dict, company_id: int | None) -> int | None:
    canonical = normalize_linkedin_url(person.get("linkedin_url"))
    if canonical:
        cur.execute("SELECT id, linkedin_url FROM people WHERE deleted_at IS NULL AND linkedin_url IS NOT NULL")
        match = next((row["id"] for row in cur.fetchall()
                      if normalize_linkedin_url(row["linkedin_url"]) == canonical), None)
        if match:
            return match
    return find_existing_person(cur, person["name"], "", company_id) if company_id else None


def person_notes(person: dict, list_name: str) -> str:
    lines = [f"From lead list {list_name} ({date.today():%d.%m.%Y})."]
    if person.get("linkedin_status"):
        lines.append(f"LinkedIn status in the list: {person['linkedin_status']}.")
    if person.get("linkedin_candidate"):
        lines.append(f"Possible LinkedIn profile (not confirmed): {person['linkedin_candidate']}")
    if person.get("notes"):
        lines.append(person["notes"])
    return "\n".join(lines)


def _company_notes(business: dict, list_name: str) -> str:
    return "\n".join(filter(None, [f"From lead list {list_name} ({date.today():%d.%m.%Y}).", business["notes"]]))


def _fill_blanks(company_id: int, business: dict) -> None:
    with db() as conn:
        conn.cursor().execute(
            """UPDATE contacts SET address = COALESCE(NULLIF(address, ''), %s),
                   website = COALESCE(NULLIF(website, ''), %s),
                   neighborhood = COALESCE(NULLIF(neighborhood, ''), %s), updated_at = NOW()
               WHERE id = %s""",
            (business["address"] or None, business["website"] or None, business["area"] or None, company_id),
        )
    log_audit(None, None, "contact.filled_from_lead_list", f"contact:{company_id}", "blank fields only")


def _save_company(business: dict, town: str, list_name: str) -> int:
    return save_organization(
        business["name"], town, source=LEAD_LIST, address=business["address"], website=business["website"],
        neighborhood=business["area"], notes=_company_notes(business, list_name), geocode_city=False,
    )


def _save_person(person: dict, company_id: int, list_name: str) -> int:
    person_id = save_person(person["name"], source=LEAD_LIST, title=person["role"], contact_id=company_id,
                            notes=person_notes(person, list_name))
    with db() as conn:
        conn.cursor().execute(
            "UPDATE people SET linkedin_url = COALESCE(linkedin_url, %s), "
            "is_linkedin_contact = is_linkedin_contact OR %s, updated_at = NOW() WHERE id = %s",
            (person.get("linkedin_url"), bool(person.get("connected")), person_id),
        )
    return person_id


def _import_company(business: dict, town: str, list_name: str, apply: bool, report: dict) -> None:
    with db() as conn:
        company_id = find_company(conn.cursor(), business["name"], town)
        existing_people = {index for index, person in enumerate(business["people"])
                           if find_person(conn.cursor(), person, company_id)}
    report["companies_existing" if company_id else "companies_new"] += 1
    report["people_existing"] += len(existing_people)
    report["people_new"] += len(business["people"]) - len(existing_people)
    if not apply:
        return
    if company_id:
        _fill_blanks(company_id, business)
    else:
        company_id = _save_company(business, town, list_name)
    report["company_ids"].append(company_id)
    for person in business["people"]:
        _save_person(person, company_id, list_name)


def import_lead_list(businesses: list[dict], *, list_name: str, default_town: str, apply: bool) -> dict:
    """Import (or, with apply=False, only count) a parsed lead list. Returns the report."""
    report = {"companies_new": 0, "companies_existing": 0, "people_new": 0, "people_existing": 0,
              "skipped_no_town": [], "company_ids": []}
    run_id = start_run("lead_import", {"list": list_name, "apply": apply}) if apply else None
    for business in businesses:
        town = business["city"] or default_town
        if not town:
            report["skipped_no_town"].append(business["name"])
            continue
        _import_company(business, town, list_name, apply, report)
    if run_id is not None:
        finish_run(run_id, "completed", summary_line(report, list_name), report)
    return report


def summary_line(report: dict, list_name: str) -> str:
    return (f"lead list {list_name}: {report['companies_new']} new companies, {report['companies_existing']} "
            f"already in the CRM, {report['people_new']} new people, {report['people_existing']} already known"
            + (f", {len(report['skipped_no_town'])} skipped (no town)" if report["skipped_no_town"] else ""))
