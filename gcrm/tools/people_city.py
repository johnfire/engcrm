"""A person lives where their company is, unless we know better.

Most people arrive without a city — LinkedIn's Connections.csv has no location —
while their company's city is resolved later. This fills a blank person city
(and country) from the company they are linked to (`people.contact_id`).

A person whose city is already set and *differs* from the company's is never
changed here: the city came from a business card or was typed in by hand, which
is evidence the person works somewhere else (a branch office, home office). Those
are reported for a human to decide.

Coordinates are left alone: distance is computed from
COALESCE(person.latitude, company.latitude), so a person with no coordinates of
their own already sits at the company's location.
"""
import re

from gcrm.db.connection import db, serialize_row
from gcrm.tools.db_audit import log_audit

# English names that cards and LinkedIn use for cities stored in German.
_EXONYMS = {
    "munich": "münchen", "nuremberg": "nürnberg", "cologne": "köln",
    "vienna": "wien", "zurich": "zürich", "zuerich": "zürich",
    "muenchen": "münchen", "nuernberg": "nürnberg", "koeln": "köln",
}


def city_key(city: str | None) -> str:
    """Compare cities by name only: no postal code, case or spacing differences."""
    text = re.sub(r"\b\d{4,5}\b", " ", (city or "").casefold())
    text = re.sub(r"\s+", " ", text).strip(" ,")
    return _EXONYMS.get(text, text)


_LINKED = (
    "SELECT p.id, p.name, p.city, p.country, p.source, p.created_at, "
    "c.id AS company_id, c.name AS company, c.city AS company_city, "
    "c.country AS company_country, c.city_status AS company_city_status "
    "FROM people p JOIN contacts c ON c.id = p.contact_id "
    "WHERE p.deleted_at IS NULL AND c.deleted_at IS NULL "
)


def survey() -> dict:
    """Every linked person, sorted into what would be filled, what disagrees,
    and what cannot be filled because the company has no city either."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(_LINKED + "ORDER BY c.name, p.name")
        linked = [serialize_row(dict(r)) for r in cur.fetchall()]
        cur.execute(
            "SELECT COUNT(*) AS n FROM people WHERE deleted_at IS NULL AND contact_id IS NULL "
            "AND COALESCE(TRIM(city), '') = ''"
        )
        unlinked_blank = cur.fetchone()["n"]

    report = {"fill": [], "mismatch": [], "company_has_no_city": [], "same": 0,
              "unlinked_without_city": unlinked_blank}
    for row in linked:
        person, company = city_key(row["city"]), city_key(row["company_city"])
        if not company:
            if not person:
                report["company_has_no_city"].append(row)
        elif not person:
            report["fill"].append(row)
        elif person == company:
            report["same"] += 1
        else:
            report["mismatch"].append(row)
    return report


def fill_blank_cities(person_ids: list[int]) -> int:
    """Copy the company's city and country onto these people. Only a person whose
    city is still blank and whose company still has one is touched, so a row
    edited since the preview is skipped rather than overwritten."""
    if not person_ids:
        return 0
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE people p
               SET city = TRIM(c.city), country = COALESCE(NULLIF(TRIM(c.country), ''), p.country),
                   updated_at = NOW()
              FROM contacts c
             WHERE c.id = p.contact_id
               AND p.id = ANY(%s)
               AND p.deleted_at IS NULL AND c.deleted_at IS NULL
               AND COALESCE(TRIM(p.city), '') = ''
               AND COALESCE(TRIM(c.city), '') <> ''
            """,
            (person_ids,),
        )
        updated = cur.rowcount
    log_audit(None, None, "people.city_from_company", f"{updated} people", "filled blank city")
    return updated
