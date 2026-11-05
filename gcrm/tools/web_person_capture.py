"""Company-aware manual person entry, with one transaction for the person and conversation."""
from gcrm.db.connection import db
from gcrm.sources import MANUAL_WEB
from gcrm.tools.db_audit import log_audit
from gcrm.tools.db_contact_dates import CONTACT_TIMEZONE, contact_day_sql
from gcrm.tools.db_people import find_existing_person, save_person
from gcrm.tools.db_people_interactions import insert_person_note

SPOKEN_NOTE = "Spoke in person when saving this contact."


class ExistingPerson(ValueError):
    def __init__(self, person_id: int):
        super().__init__("This person already exists")
        self.person_id = person_id


def capture_choices(contact_id: int | None = None, query: str = "") -> dict:
    """Only live records in the request's workspace are available to choose."""
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id, name, city, country, decision_maker FROM contacts "
                       "WHERE deleted_at IS NULL ORDER BY lower(name), id")
        organizations = [dict(row) for row in cursor.fetchall()]
        organization = next((company for company in organizations if company["id"] == contact_id), None)
        matches = []
        if organization and query.strip():
            cursor.execute(
                "SELECT id, name, email FROM people WHERE deleted_at IS NULL "
                "AND (contact_id IS NULL OR contact_id=%s) AND name ILIKE %s ORDER BY lower(name), id LIMIT 30",
                (contact_id, f"%{query.strip()}%"),
            )
            matches = [dict(row) for row in cursor.fetchall()]
    return {"organizations": organizations, "organization": organization, "person_matches": matches}


def _lock_company(cursor, contact_id: int | None) -> dict:
    if contact_id is None:
        return {}
    cursor.execute("SELECT id, name, city, country FROM contacts "
                   "WHERE id=%s AND deleted_at IS NULL FOR UPDATE", (contact_id,))
    organization = cursor.fetchone()
    if organization is None:
        raise ValueError("Organization not found")
    return dict(organization)


def _record_spoken_today(cursor, person_id: int) -> bool:
    cursor.execute("SELECT 1 FROM people_interactions WHERE person_id=%s AND deleted_at IS NULL "
                   f"AND {contact_day_sql('person', 'occurred_at')}=(NOW() AT TIME ZONE '{CONTACT_TIMEZONE}')::date "
                   "AND method='visit' AND note=%s",
                   (person_id, SPOKEN_NOTE))
    if cursor.fetchone():
        return False
    insert_person_note(cursor, person_id, "visit", SPOKEN_NOTE)
    return True


def save_company_person(fields: dict, contact_id: int | None, stage: str, offer: str,
                        allow_duplicate: bool, spoke_today: bool) -> int:
    with db() as connection:
        cursor = connection.cursor()
        company = _lock_company(cursor, contact_id)
        duplicate = find_existing_person(cursor, fields["name"], fields.get("email") or "", contact_id)
        if duplicate and not allow_duplicate:
            raise ExistingPerson(duplicate)
        person_fields = {key: value or "" for key, value in fields.items()}
        person_fields["city"] = person_fields.get("city") or company.get("city") or ""
        person_fields["country"] = person_fields.get("country") or company.get("country") or "DE"
        person_id = save_person(**person_fields, source=MANUAL_WEB, contact_id=contact_id,
                                pipeline_stage=stage, offer=offer, allow_duplicate=allow_duplicate,
                                cursor=cursor, geocode_city=bool(fields.get("city")))
        noted = _record_spoken_today(cursor, person_id) if spoke_today else False
    if noted:
        log_audit(None, None, "person.note_added", f"person:{person_id}", "visit")
    return person_id


def link_existing_person(person_id: int, contact_id: int, spoke_today: bool) -> None:
    with db() as connection:
        cursor = connection.cursor()
        _lock_company(cursor, contact_id)
        cursor.execute("SELECT contact_id FROM people WHERE id=%s AND deleted_at IS NULL FOR UPDATE",
                       (person_id,))
        person = cursor.fetchone()
        if person is None or person["contact_id"] not in (None, contact_id):
            raise ValueError("Choose an unlinked person or someone already at this organization")
        cursor.execute("UPDATE people SET contact_id=%s, updated_at=NOW() WHERE id=%s", (contact_id, person_id))
        cursor.execute("DELETE FROM person_match_rejections WHERE person_id=%s AND contact_id=%s",
                       (person_id, contact_id))
        noted = _record_spoken_today(cursor, person_id) if spoke_today else False
    log_audit(None, None, "person.linked", f"person:{person_id}", f"contact:{contact_id}")
    if noted:
        log_audit(None, None, "person.note_added", f"person:{person_id}", "visit")
