"""Offers: what a workspace sells — consulting, an app, anything added later.

A deal (gcrm/tools/db_deals.py) is one offer pitched to one organization or
person. Offers are managed on the Offers page; an offer with deals is archived,
never deleted, so its history keeps its name.
"""
import re
import unicodedata

from gcrm.db.connection import db
from gcrm.tools.db_audit import log_audit

REVENUE_KINDS = ("one_off", "subscription")
MAX_NAME = 80


def default_workspace_id(cur) -> int:
    cur.execute("SELECT id FROM workspaces WHERE slug = 'default'")
    return cur.fetchone()["id"]


def resolve_workspace(cur, workspace_id: int | None) -> int:
    """The given workspace, or the default one for the shared admin login."""
    return workspace_id if workspace_id is not None else default_workspace_id(cur)


def slugify(name: str) -> str:
    """A stable key from a name: 'LeGuild.art' -> 'leguild-art'. Matches the
    pattern db_deals accepts for offer slugs."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")[:40].strip("-")
    return slug or "offer"


def list_offers(workspace_id: int | None, include_archived: bool = False) -> list[dict]:
    """The workspace's offers in their display order, with how many live deals each has."""
    with db() as conn:
        cur = conn.cursor()
        workspace = resolve_workspace(cur, workspace_id)
        archived = "" if include_archived else "AND o.archived_at IS NULL"
        cur.execute(
            f"""
            SELECT o.id, o.slug, o.name, o.website, o.revenue_kind, o.sort_order,
                   o.archived_at IS NOT NULL AS archived,
                   (SELECT COUNT(*) FROM deals d WHERE d.offer_id = o.id AND d.deleted_at IS NULL) AS deals
              FROM offers o
             WHERE o.workspace_id = %s {archived}
             ORDER BY o.archived_at IS NOT NULL, o.sort_order, o.id
            """,
            (workspace,),
        )
        return [dict(row) for row in cur.fetchall()]


def get_offer(workspace_id: int | None, offer_id: int) -> dict | None:
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, slug, name, website, revenue_kind, archived_at IS NOT NULL AS archived "
            "FROM offers WHERE id = %s AND workspace_id = %s",
            (offer_id, resolve_workspace(cur, workspace_id)),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def _clean(name: str, website: str, revenue_kind: str) -> tuple[str, str | None, str]:
    name = (name or "").strip()
    if not name or len(name) > MAX_NAME:
        raise ValueError(f"an offer needs a name of at most {MAX_NAME} characters")
    if revenue_kind not in REVENUE_KINDS:
        raise ValueError("unknown revenue kind")
    return name, (website or "").strip() or None, revenue_kind


def create_offer(workspace_id: int | None, name: str, website: str = "", revenue_kind: str = "one_off") -> int:
    """Add an offer at the end of the list. The slug comes from the name and is
    made unique within the workspace; it never changes afterwards."""
    name, website, revenue_kind = _clean(name, website, revenue_kind)
    with db() as conn:
        cur = conn.cursor()
        workspace = resolve_workspace(cur, workspace_id)
        base = slugify(name)
        cur.execute("SELECT slug FROM offers WHERE workspace_id = %s", (workspace,))
        taken = {row["slug"] for row in cur.fetchall()}
        slug, n = base, 2
        while slug in taken:
            suffix = f"-{n}"
            slug, n = base[: 40 - len(suffix)] + suffix, n + 1
        cur.execute(
            "INSERT INTO offers (workspace_id, slug, name, website, revenue_kind, sort_order) "
            "VALUES (%s, %s, %s, %s, %s, "
            "(SELECT COALESCE(MAX(sort_order), 0) + 10 FROM offers WHERE workspace_id = %s)) RETURNING id",
            (workspace, slug, name, website, revenue_kind, workspace),
        )
        offer_id = cur.fetchone()["id"]
    log_audit(None, None, "offer.created", f"offer:{offer_id}", slug)
    return offer_id


def update_offer(workspace_id: int | None, offer_id: int, name: str, website: str, revenue_kind: str) -> bool:
    """Rename an offer or change its website or revenue kind. The slug stays."""
    name, website, revenue_kind = _clean(name, website, revenue_kind)
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE offers SET name = %s, website = %s, revenue_kind = %s WHERE id = %s AND workspace_id = %s",
            (name, website, revenue_kind, offer_id, resolve_workspace(cur, workspace_id)),
        )
        found = cur.rowcount > 0
    if found:
        log_audit(None, None, "offer.updated", f"offer:{offer_id}", name)
    return found


def set_offer_archived(workspace_id: int | None, offer_id: int, archived: bool) -> bool:
    """Hide an offer from the pickers, or bring it back. Its deals stay as they are."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE offers SET archived_at = CASE WHEN %s THEN COALESCE(archived_at, NOW()) END "
            "WHERE id = %s AND workspace_id = %s",
            (archived, offer_id, resolve_workspace(cur, workspace_id)),
        )
        found = cur.rowcount > 0
    if found:
        log_audit(None, None, "offer.archived" if archived else "offer.restored", f"offer:{offer_id}", "")
    return found


def move_offer(workspace_id: int | None, offer_id: int, direction: str) -> bool:
    """Swap an offer with its neighbour above ('up') or below ('down')."""
    if direction not in ("up", "down"):
        raise ValueError("direction is up or down")
    with db() as conn:
        cur = conn.cursor()
        workspace = resolve_workspace(cur, workspace_id)
        cur.execute(
            "SELECT id, sort_order FROM offers WHERE workspace_id = %s AND archived_at IS NULL "
            "ORDER BY sort_order, id FOR UPDATE",
            (workspace,),
        )
        rows = [dict(row) for row in cur.fetchall()]
        index = next((i for i, row in enumerate(rows) if row["id"] == offer_id), None)
        if index is None:
            return False
        other = index - 1 if direction == "up" else index + 1
        if not 0 <= other < len(rows):
            return True
        rows[index], rows[other] = rows[other], rows[index]
        for position, row in enumerate(rows):
            cur.execute("UPDATE offers SET sort_order = %s WHERE id = %s", ((position + 1) * 10, row["id"]))
    return True
