"""
People (individual humans) database operations. Split out of db.py to keep that
file under the 600-line limit. A person is optionally linked to their company
contact via people.contact_id — e.g. the individual on a scanned business card.
"""
import logging

from gcrm.db.connection import db, serialize_row

logger = logging.getLogger(__name__)


def _refresh_met_at(cur, person_id: int, met_at: str) -> int:
    """
    A re-scan carries a freshly typed met_at, so write it to the row we deduped
    onto — otherwise the new place is silently dropped. Returns person_id so the
    dedup branches can `return _refresh_met_at(...)` directly.

    An empty met_at is a no-op: re-saving a card without typing a place must not
    erase the place already recorded.
    """
    if not met_at:
        return person_id
    cur.execute(
        "UPDATE people SET met_at = %s, updated_at = NOW() WHERE id = %s",
        (met_at, person_id),
    )
    logger.info("save_person: updated met_at on existing person id=%d", person_id)
    return person_id


def save_person(
    name: str,
    *,
    title: str = "",
    email: str = "",
    phone: str = "",
    website: str = "",
    city: str = "",
    country: str = "DE",
    relationship: str = "",
    notes: str = "",
    met_at: str = "",
    contact_id: int | None = None,
    source: str = "",
) -> int:
    """
    Insert a person, optionally linked to their company contact. Returns the new
    person's id, or the id of an existing match — dedup by email, else by
    (name, contact_id). Never returns 0, so the caller always gets a usable id.

    On a dedup hit the existing row is left as-is except for `met_at`, which a
    re-scan is allowed to update (a person can be met somewhere new). Every
    other field still belongs to whoever created the row first.
    """
    with db() as conn:
        cur = conn.cursor()
        if email:
            cur.execute("SELECT id FROM people WHERE lower(email) = lower(%s)", (email,))
            existing = cur.fetchone()
            if existing:
                logger.debug("save_person: email duplicate — %s (%s)", name, email)
                return _refresh_met_at(cur, existing["id"], met_at)
        # IS NOT DISTINCT FROM so a NULL contact_id matches another NULL.
        cur.execute(
            "SELECT id FROM people WHERE lower(name) = lower(%s) "
            "AND contact_id IS NOT DISTINCT FROM %s",
            (name, contact_id),
        )
        existing = cur.fetchone()
        if existing:
            logger.debug("save_person: name duplicate — %s (contact_id=%s)", name, contact_id)
            return _refresh_met_at(cur, existing["id"], met_at)

        cur.execute(
            """
            INSERT INTO people
                (name, title, email, phone, website, city, country, relationship,
                 notes, met_at, contact_id, source)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (name, title or None, email or None, phone or None, website or None,
             city or None, country or None, relationship or None, notes or None,
             met_at or None, contact_id, source or None),
        )
        person_id = cur.fetchone()["id"]
        logger.info("save_person: created id=%d  %s (contact_id=%s)", person_id, name, contact_id)
        return person_id


# Whitelisted so the UPDATE below builds its column list from constants only —
# never from submitted form keys. Deliberately excludes contact_id (the company
# link is a relation, not a text field) and source/created_at (provenance).
EDITABLE_COLUMNS = (
    "name", "title", "email", "phone", "website",
    "city", "country", "relationship", "notes", "met_at",
)


def update_person(person_id: int, values: dict) -> bool:
    """
    Write the editable fields of one person. Only EDITABLE_COLUMNS keys present
    in `values` are written; blank strings become NULL. Returns False when the
    person does not exist, so the caller can 404 rather than silently no-op.
    """
    updates = {
        column: ((values.get(column) or "").strip() or None)
        for column in EDITABLE_COLUMNS
        if column in values
    }
    if not updates:
        return False

    assignments = ", ".join(f"{column} = %s" for column in updates)
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            f"UPDATE people SET {assignments}, updated_at = NOW() WHERE id = %s",
            list(updates.values()) + [person_id],
        )
        if cur.rowcount == 0:
            logger.warning("update_person: no person with id=%s", person_id)
            return False
    logger.info("update_person: updated id=%d (%s)", person_id, ", ".join(updates))
    return True


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
