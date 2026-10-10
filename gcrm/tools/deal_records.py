"""Working with deals one at a time: the Deals panel on an organization's or a
person's page, and the matching mobile endpoints.

Every function checks the deal (or its owner) belongs to `workspace_id` when one
is given; the shared admin login (workspace None) sees every workspace, as on
the rest of the site. Next steps are also written to the owner's log, so the
history of what was planned stays — the same rule people_next_step follows.
"""
from datetime import date

from gcrm.db.connection import db, serialize_row
from gcrm.organization_state import DEFAULT_STAGE, DEFAULT_STATUS, coerce_stage, coerce_status
from gcrm.tools.db_audit import log_audit

OWNERS = {"organization": "contact_id", "person": "person_id"}
NEXT_STEP_MAX = 500
LOG_METHOD, DONE_METHOD = "next_step", "next_step_done"

_DEAL_COLUMNS = """
    d.id, d.offer_id, o.slug AS offer_slug, o.name AS offer_name, o.revenue_kind,
    o.archived_at IS NOT NULL AS offer_archived, d.contact_id, d.person_id,
    d.pipeline_stage, d.status, d.next_step, d.next_step_date, d.notes,
    d.contact_person_id, cp.name AS contact_person_name, d.created_at, d.updated_at
"""
_DEAL_FROM = """
    FROM deals d JOIN offers o ON o.id = d.offer_id
    LEFT JOIN people cp ON cp.id = d.contact_person_id AND cp.deleted_at IS NULL
"""


class DealNotFound(LookupError):
    """No such deal (or owner, or offer) in this workspace."""


def _scope(workspace_id: int | None, column: str = "d.workspace_id") -> tuple[str, list]:
    return ("", []) if workspace_id is None else (f" AND {column} = %s", [workspace_id])


def _column(owner: str) -> str:
    if owner not in OWNERS:
        raise ValueError(f"unknown deal owner: {owner!r}")
    return OWNERS[owner]


def get_deals(owner: str, owner_id: int, workspace_id: int | None = None) -> list[dict]:
    """The live deals an organization or person owns, in offer order."""
    scope, params = _scope(workspace_id)
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            f"SELECT {_DEAL_COLUMNS} {_DEAL_FROM} WHERE d.{_column(owner)} = %s AND d.deleted_at IS NULL{scope} "
            "ORDER BY o.sort_order, o.id",
            [owner_id, *params],
        )
        return [serialize_row(dict(row)) for row in cur.fetchall()]


def get_deals_as_contact_person(person_id: int, workspace_id: int | None = None) -> list[dict]:
    """Organizations' deals that name this person as their contact person."""
    scope, params = _scope(workspace_id)
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            f"SELECT {_DEAL_COLUMNS}, c.name AS organization_name {_DEAL_FROM} "
            "JOIN contacts c ON c.id = d.contact_id AND c.deleted_at IS NULL "
            f"WHERE d.contact_person_id = %s AND d.deleted_at IS NULL{scope} ORDER BY o.sort_order, c.name",
            [person_id, *params],
        )
        return [serialize_row(dict(row)) for row in cur.fetchall()]


def get_deal(cur, deal_id: int, workspace_id: int | None = None) -> dict:
    scope, params = _scope(workspace_id)
    cur.execute(
        f"SELECT {_DEAL_COLUMNS} {_DEAL_FROM} WHERE d.id = %s AND d.deleted_at IS NULL{scope}",
        [deal_id, *params],
    )
    row = cur.fetchone()
    if row is None:
        raise DealNotFound(f"no deal {deal_id}")
    return dict(row)


def add_deal(owner: str, owner_id: int, offer_id: int, workspace_id: int | None = None,
             stage: str = DEFAULT_STAGE, status: str = DEFAULT_STATUS) -> int:
    """Pitch an offer to an organization or person. Adding an offer they already
    have returns the existing deal rather than a second one. Raises DealNotFound
    when the owner or the offer is not in the owner's workspace, or the offer is archived."""
    table = "contacts" if owner == "organization" else "people"
    column = _column(owner)
    scope, params = _scope(workspace_id, "x.workspace_id")
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            f"""
            INSERT INTO deals (workspace_id, offer_id, {column}, pipeline_stage, status)
            SELECT o.workspace_id, o.id, x.id, %s, %s
              FROM {table} x
              JOIN offers o ON o.id = %s AND o.archived_at IS NULL
                           AND o.workspace_id = COALESCE(x.workspace_id, (SELECT id FROM workspaces WHERE slug = 'default'))
             WHERE x.id = %s AND x.deleted_at IS NULL{scope}
            ON CONFLICT DO NOTHING
            RETURNING id
            """,
            [coerce_stage(stage), coerce_status(status), offer_id, owner_id, *params],
        )
        row = cur.fetchone()
        if row is None:
            cur.execute(
                f"SELECT id FROM deals WHERE {column} = %s AND offer_id = %s AND deleted_at IS NULL",
                (owner_id, offer_id),
            )
            row = cur.fetchone()
            if row is None:
                raise DealNotFound(f"cannot add offer {offer_id} to {owner} {owner_id}")
            return row["id"]
        deal_id = row["id"]
    log_audit(None, None, "deal.created", f"deal:{deal_id}", f"{owner}:{owner_id} offer:{offer_id}")
    return deal_id


_UNSET = object()


def update_deal(deal_id: int, workspace_id: int | None = None, *, stage: str | None = None,
                status: str | None = None, contact_person_id=_UNSET) -> dict:
    """Change a deal's stage, status and/or contact person; None leaves stage or
    status as they are. A contact person must be someone linked to the deal's
    organization; pass None to clear it. Returns the deal as stored."""
    with db() as conn:
        cur = conn.cursor()
        deal = get_deal(cur, deal_id, workspace_id)
        assignments, values = [], []
        if stage is not None:
            assignments.append("pipeline_stage = %s")
            values.append(coerce_stage(stage))
        if status is not None:
            assignments.append("status = %s")
            values.append(coerce_status(status))
        if contact_person_id is not _UNSET:
            if contact_person_id is not None:
                if deal["contact_id"] is None:
                    raise ValueError("only an organization's deal has a contact person")
                cur.execute(
                    "SELECT 1 FROM people WHERE id = %s AND contact_id = %s AND deleted_at IS NULL",
                    (contact_person_id, deal["contact_id"]),
                )
                if cur.fetchone() is None:
                    raise ValueError("the contact person must work at the organization")
            assignments.append("contact_person_id = %s")
            values.append(contact_person_id)
        if assignments:
            cur.execute(f"UPDATE deals SET {', '.join(assignments)} WHERE id = %s", [*values, deal_id])
        deal = get_deal(cur, deal_id, workspace_id)
    log_audit(None, None, "deal.updated", f"deal:{deal_id}", f"{deal['pipeline_stage']}/{deal['status']}")
    return serialize_row(deal)


def remove_deal(deal_id: int, workspace_id: int | None = None) -> None:
    """Stop pitching this offer: the deal is soft-deleted, its history stays."""
    with db() as conn:
        cur = conn.cursor()
        get_deal(cur, deal_id, workspace_id)
        cur.execute("UPDATE deals SET deleted_at = NOW() WHERE id = %s", (deal_id,))
    log_audit(None, None, "deal.removed", f"deal:{deal_id}", "removed")


def log_entry(text: str, due: date | None) -> str:
    return f"{text} ({due.isoformat()})" if due else text


def write_next_step(cur, deal: dict, text: str, due: date | None) -> bool:
    """Store a deal's next step and log the change on its owner (a cleared step
    is logged as done). Returns whether anything was logged. The caller has
    validated `text` and `due` and checked they differ from what is stored."""
    previous = (deal["next_step"] or "").strip()
    cur.execute("UPDATE deals SET next_step = %s, next_step_date = %s WHERE id = %s",
                (text or None, due, deal["id"]))
    if not (text or previous):
        return False
    method, note = (LOG_METHOD, log_entry(text, due)) if text else (DONE_METHOD, f"✓ {previous}")
    if deal["person_id"] is not None:
        cur.execute(
            "INSERT INTO people_interactions (person_id, method, note, offer_id) VALUES (%s, %s, %s, %s)",
            (deal["person_id"], method, note, deal["offer_id"]),
        )
    else:
        cur.execute(
            "INSERT INTO interactions (contact_id, interaction_date, method, summary, offer_id, workspace_id) "
            "SELECT id, CURRENT_DATE, %s, %s, %s, workspace_id FROM contacts WHERE id = %s",
            (method, note, deal["offer_id"], deal["contact_id"]),
        )
    return True


def check_next_step(text: str | None, due: date | None) -> str:
    text = (text or "").strip()
    if len(text) > NEXT_STEP_MAX:
        raise ValueError(f"a next step is at most {NEXT_STEP_MAX} characters")
    if not text and due is not None:
        raise ValueError("a due date needs a next step")
    return text


def set_deal_next_step(deal_id: int, text: str | None, due: date | None,
                       workspace_id: int | None = None) -> dict:
    """Set a deal's next step, or clear it with a blank `text`. Saving what is
    already there writes nothing. Returns {next_step, next_step_date, logged}."""
    text = check_next_step(text, due)
    with db() as conn:
        cur = conn.cursor()
        deal = get_deal(cur, deal_id, workspace_id)
        if ((deal["next_step"] or "").strip(), deal["next_step_date"]) == (text, due):
            return {"next_step": text or None, "next_step_date": due, "logged": False}
        logged = write_next_step(cur, deal, text, due)
    log_audit(None, None, "deal.next_step", f"deal:{deal_id}", "set" if text else "cleared")
    return {"next_step": text or None, "next_step_date": due, "logged": logged}


def contact_people(contact_id: int) -> list[dict]:
    """Who can be named as an organization's contact person: the people linked to it."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, name, title FROM people WHERE contact_id = %s AND deleted_at IS NULL "
                    "ORDER BY lower(name)", (contact_id,))
        return [dict(row) for row in cur.fetchall()]


# --- Which offer a log entry is about ----------------------------------------

def _open_deal_offers(cur, owner: str, owner_id: int) -> list[int]:
    """The offers this organization or person has an open deal for (any stage but
    not_in_pipeline). A person's include their organization's."""
    if owner == "organization":
        cur.execute("SELECT DISTINCT offer_id FROM deals WHERE contact_id = %s AND deleted_at IS NULL "
                    "AND pipeline_stage <> 'not_in_pipeline'", (owner_id,))
    else:
        cur.execute(
            "SELECT DISTINCT d.offer_id FROM deals d LEFT JOIN people p ON p.id = %s "
            "WHERE d.deleted_at IS NULL AND d.pipeline_stage <> 'not_in_pipeline' "
            "AND (d.person_id = %s OR (p.contact_id IS NOT NULL AND d.contact_id = p.contact_id))",
            (owner_id, owner_id),
        )
    return [row["offer_id"] for row in cur.fetchall()]


GENERAL = ("", "0", "general")


def resolve_log_offer(owner: str, owner_id: int, choice: str | int | None,
                      workspace_id: int | None = None) -> int | None:
    """The offer id a new log entry is about, or None for "general".

    `choice` None means nobody chose (an older phone build, an agent): the one
    open deal's offer when there is exactly one, else general. "", "0" and
    "general" mean general; an offer id or slug must be an active offer of the
    owner's workspace (else ValueError)."""
    _column(owner)
    with db() as conn:
        cur = conn.cursor()
        if choice is None:
            offers = _open_deal_offers(cur, owner, owner_id)
            return offers[0] if len(offers) == 1 else None
        choice = str(choice).strip()
        if choice in GENERAL:
            return None
        table = "contacts" if owner == "organization" else "people"
        column = "o.id = %s" if choice.isdigit() else "o.slug = %s"
        cur.execute(
            f"SELECT o.id FROM offers o JOIN {table} x ON x.id = %s "
            "AND o.workspace_id = COALESCE(x.workspace_id, (SELECT id FROM workspaces WHERE slug = 'default')) "
            f"WHERE {column} AND o.archived_at IS NULL"
            + ("" if workspace_id is None else " AND o.workspace_id = %s"),
            [owner_id, int(choice) if choice.isdigit() else choice]
            + ([] if workspace_id is None else [workspace_id]),
        )
        row = cur.fetchone()
        if row is None:
            raise ValueError(f"unknown offer: {choice!r}")
        return row["id"]


def log_offer_default(owner: str, owner_id: int) -> int | None:
    """What a log form preselects: the one open deal's offer, else general."""
    return resolve_log_offer(owner, owner_id, None)
