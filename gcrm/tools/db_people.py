"""
People (individual humans) database operations. Split out of db.py to keep that
file under the 600-line limit. A person is optionally linked to their company
contact via people.contact_id — e.g. the individual on a scanned business card.
"""
import logging

from gcrm.db.connection import db, serialize_row

logger = logging.getLogger(__name__)


def save_person(
    name: str,
    *,
    title: str = "",
    email: str = "",
    phone: str = "",
    website: str = "",
    city: str = "",
    country: str = "DE",
    notes: str = "",
    contact_id: int | None = None,
    source: str = "",
) -> int:
    """
    Insert a person, optionally linked to their company contact. Returns the new
    person's id, or the id of an existing match — dedup by email, else by
    (name, contact_id). Never returns 0, so the caller always gets a usable id.
    """
    with db() as conn:
        cur = conn.cursor()
        if email:
            cur.execute("SELECT id FROM people WHERE lower(email) = lower(%s)", (email,))
            existing = cur.fetchone()
            if existing:
                logger.debug("save_person: email duplicate — %s (%s)", name, email)
                return existing["id"]
        # IS NOT DISTINCT FROM so a NULL contact_id matches another NULL.
        cur.execute(
            "SELECT id FROM people WHERE lower(name) = lower(%s) "
            "AND contact_id IS NOT DISTINCT FROM %s",
            (name, contact_id),
        )
        existing = cur.fetchone()
        if existing:
            logger.debug("save_person: name duplicate — %s (contact_id=%s)", name, contact_id)
            return existing["id"]

        cur.execute(
            """
            INSERT INTO people
                (name, title, email, phone, website, city, country, notes, contact_id, source)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (name, title or None, email or None, phone or None, website or None,
             city or None, country or None, notes or None, contact_id, source or None),
        )
        person_id = cur.fetchone()["id"]
        logger.info("save_person: created id=%d  %s (contact_id=%s)", person_id, name, contact_id)
        return person_id


_SELECT_WITH_COMPANY = (
    "SELECT person.*, company.name AS company "
    "FROM people person "
    "LEFT JOIN contacts company ON company.id = person.contact_id "
)

# Whitelisted so `sort` can be trusted straight into an f-string ORDER BY below.
SORT_COLUMNS = {
    "created_at": "person.created_at",
    "name":       "lower(person.name)",
}


def get_people(search: str = "", sort: str = "created_at", dir: str = "desc") -> list[dict]:
    """All people (optionally filtered by name/email/city), sorted by `sort`
    (created_at|name; default newest-added-first), each annotated with their
    linked company name."""
    sort_col = SORT_COLUMNS.get(sort, SORT_COLUMNS["created_at"])
    sort_dir = "DESC" if dir == "desc" else "ASC"
    with db() as conn:
        cur = conn.cursor()
        if search:
            like = f"%{search}%"
            cur.execute(
                _SELECT_WITH_COMPANY + "WHERE person.name ILIKE %s OR person.email ILIKE %s "
                f"OR person.city ILIKE %s ORDER BY {sort_col} {sort_dir}",
                (like, like, like),
            )
        else:
            cur.execute(_SELECT_WITH_COMPANY + f"ORDER BY {sort_col} {sort_dir}")
        return [serialize_row(dict(row)) for row in cur.fetchall()]


def get_person(person_id: int) -> dict | None:
    """One person with their linked company name, or None if not found."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(_SELECT_WITH_COMPANY + "WHERE person.id = %s", (person_id,))
        row = cur.fetchone()
        return serialize_row(dict(row)) if row else None
