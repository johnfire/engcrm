"""Deals: one offer, one organization or person, with its own stage and status.

The stage used to live on the organization (`contacts`) and the person
(`people`); migration 064 moved it here so a contact can be pitched several
offers. See docs/plans/2026-10-10-offers-and-deals-design.md.

Reads join a contact to its deal for one offer with the *_deal_join fragments,
selecting the deal's columns under the names the rest of the app already uses
(`pipeline_stage`, `status`, `next_step`, `next_step_date`). Writes go through
the functions below, which take the caller's cursor so they share its
transaction. Until offers become visible (phase 2) every caller uses
CONSULTING, the offer the agents work for.
"""
import logging
import re

from gcrm.organization_state import (
    DEFAULT_STAGE,
    DEFAULT_STATUS,
    PIPELINE_STAGES,
    coerce_stage,
    coerce_status,
)

logger = logging.getLogger(__name__)

CONSULTING = "consulting"

# Offer slugs are interpolated into SQL (the join fragments are plain strings,
# shared by queries with their own parameter lists), so a slug is checked
# against this pattern before it gets anywhere near a statement.
_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
_ALIAS = re.compile(r"^[a-z_][a-z0-9_]{0,30}$")


def _checked(slug: str) -> str:
    if not _SLUG.match(slug):
        raise ValueError(f"not an offer slug: {slug!r}")
    return slug


def _alias(name: str) -> str:
    if not _ALIAS.match(name):
        raise ValueError(f"not a SQL alias: {name!r}")
    return name


def offer_id_sql(workspace_expr: str, offer: str = CONSULTING) -> str:
    """SQL for the id of `offer` in the workspace `workspace_expr` evaluates to."""
    return f"offer_id_for({workspace_expr}, '{_checked(offer)}')"


def organization_deal_join(organization: str = "c", deal: str = "d", offer: str = CONSULTING) -> str:
    """`LEFT JOIN` the organization aliased `organization` to its live deal for
    `offer`, aliased `deal`. An organization without one gets NULLs."""
    organization, deal = _alias(organization), _alias(deal)
    return (
        f" LEFT JOIN deals {deal} ON {deal}.contact_id = {organization}.id "
        f"AND {deal}.deleted_at IS NULL "
        f"AND {deal}.offer_id = {offer_id_sql(f'{organization}.workspace_id', offer)} "
    )


def person_deal_join(person: str = "p", deal: str = "pd", offer: str = CONSULTING) -> str:
    """`LEFT JOIN` the person aliased `person` to the deal they own for `offer`."""
    person, deal = _alias(person), _alias(deal)
    return (
        f" LEFT JOIN deals {deal} ON {deal}.person_id = {person}.id "
        f"AND {deal}.deleted_at IS NULL "
        f"AND {deal}.offer_id = {offer_id_sql(f'{person}.workspace_id', offer)} "
    )


def set_organization_deal(
    cur,
    contact_id: int,
    *,
    stage: str | None = None,
    status: str | None = None,
    offer: str = CONSULTING,
) -> bool:
    """Set the stage and/or status of an organization's deal for `offer`,
    creating the deal when there is none (missing values start at the defaults).
    A value left as None keeps what is there. Returns False when there is no
    such organization."""
    stage = None if stage is None else coerce_stage(stage)
    status = None if status is None else coerce_status(status)
    cur.execute(
        f"""
        INSERT INTO deals (workspace_id, offer_id, contact_id, pipeline_stage, status)
        SELECT COALESCE(c.workspace_id, (SELECT id FROM workspaces WHERE slug = 'default')),
               {offer_id_sql('c.workspace_id', offer)}, c.id,
               COALESCE(%s, %s), COALESCE(%s, %s)
          FROM contacts c WHERE c.id = %s
        ON CONFLICT (offer_id, contact_id) WHERE contact_id IS NOT NULL AND deleted_at IS NULL
        DO UPDATE SET pipeline_stage = COALESCE(%s, deals.pipeline_stage),
                      status = COALESCE(%s, deals.status)
        """,
        (stage, DEFAULT_STAGE, status, DEFAULT_STATUS, contact_id, stage, status),
    )
    return bool(cur.rowcount)


def update_organization_status(
    cur,
    contact_id: int,
    status: str,
    *,
    only_from: tuple[str, ...] | None = None,
    not_from: tuple[str, ...] | None = None,
    offer: str = CONSULTING,
) -> int:
    """Move an organization's existing deal for `offer` to `status`, only when
    its current status is in `only_from` / not in `not_from`. Never creates a
    deal. Returns the number of deals changed (0 or 1)."""
    conditions, params = [], [coerce_status(status), contact_id]
    if only_from is not None:
        conditions.append("AND d.status = ANY(%s)")
        params.append(list(only_from))
    if not_from is not None:
        conditions.append("AND d.status <> ALL(%s)")
        params.append(list(not_from))
    cur.execute(
        f"""
        UPDATE deals d SET status = %s
          FROM contacts c
         WHERE c.id = %s AND d.contact_id = c.id AND d.deleted_at IS NULL
           AND d.offer_id = {offer_id_sql('c.workspace_id', offer)}
           {' '.join(conditions)}
        """,
        params,
    )
    return cur.rowcount


def get_person_deal(cur, person_id: int, offer: str = CONSULTING) -> dict | None:
    """The live deal `person_id` owns for `offer`, or None."""
    cur.execute(
        f"SELECT d.* FROM people p {person_deal_join('p', 'd', offer)} "
        "WHERE p.id = %s AND d.id IS NOT NULL",
        (person_id,),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def set_person_stage(cur, person_id: int, stage: str | None, offer: str = CONSULTING) -> str | None:
    """Set the stage of the deal a person owns for `offer`; blank or None
    clears it. Returns the stage the person ends up with.

    Clearing removes the deal — unless it holds an open next step, which would
    be lost with it. Then the deal stays, as a candidate: the same rule the
    migration applied to people who had a next step but no stage.
    Raises ValueError for a stage that is not in PIPELINE_STAGES."""
    stage = (stage or "").strip() or None
    if stage is not None and stage not in PIPELINE_STAGES:
        raise ValueError(f"unknown pipeline stage: {stage!r}")
    deal = get_person_deal(cur, person_id, offer)
    if stage is None:
        if deal is None:
            return None
        if deal["next_step"] or deal["next_step_date"]:
            if deal["pipeline_stage"] != DEFAULT_STAGE:
                cur.execute("UPDATE deals SET pipeline_stage = %s WHERE id = %s", (DEFAULT_STAGE, deal["id"]))
            return DEFAULT_STAGE
        cur.execute("UPDATE deals SET deleted_at = NOW() WHERE id = %s", (deal["id"],))
        return None
    if deal is not None:
        cur.execute("UPDATE deals SET pipeline_stage = %s WHERE id = %s", (stage, deal["id"]))
        return stage
    _insert_person_deal(cur, person_id, offer, stage=stage)
    return stage


def _insert_person_deal(cur, person_id: int, offer: str, *, stage: str = DEFAULT_STAGE,
                        next_step: str | None = None, next_step_date=None) -> None:
    cur.execute(
        f"""
        INSERT INTO deals (workspace_id, offer_id, person_id, pipeline_stage, next_step, next_step_date)
        SELECT COALESCE(p.workspace_id, (SELECT id FROM workspaces WHERE slug = 'default')),
               {offer_id_sql('p.workspace_id', offer)}, p.id, %s, %s, %s
          FROM people p WHERE p.id = %s
        """,
        (stage, next_step or None, next_step_date, person_id),
    )
    logger.info("deal created: person %d, offer %s, stage %s", person_id, offer, stage)


# --- Lists filtered by offer --------------------------------------------------
# The Organizations, People and Contacts lists show either one offer's pipeline
# (`offer` = its slug) or every offer at once (`offer` = None). These build the
# SQL both modes share. The owner is an organization (column contact_id) or a
# person (person_id); `alias` is the owner's alias in the caller's query.

_OWNER_COLUMNS = ("contact_id", "person_id")


def _owner(alias: str, column: str) -> tuple[str, str]:
    if column not in _OWNER_COLUMNS:
        raise ValueError(f"not a deal owner column: {column!r}")
    return _alias(alias), column


def deals_json_sql(alias: str, column: str, offer: str | None) -> str:
    """A JSON array of the owner's live deals — every offer's, or just `offer`'s —
    each {id, offer, slug, stage, status}, in offer order. Never NULL."""
    alias, column = _owner(alias, column)
    only = f"AND x.offer_id = {offer_id_sql(f'{alias}.workspace_id', offer)}" if offer else ""
    return (
        "(SELECT COALESCE(json_agg(json_build_object('id', x.id, 'offer', o.name, 'slug', o.slug, "
        "'stage', x.pipeline_stage, 'status', x.status) ORDER BY o.sort_order, o.id), '[]'::json) "
        f"FROM deals x JOIN offers o ON o.id = x.offer_id WHERE x.{column} = {alias}.id "
        f"AND x.deleted_at IS NULL {only})"
    )


def deal_filters(alias: str, column: str, offer: str | None, stage: str = "",
                 status: str = "", only_pitched: bool = True) -> tuple[list[str], list]:
    """WHERE conditions (and their params) for one offer's pipeline: the owner
    has a live deal for `offer` (unless `only_pitched` is off), at `stage`
    and/or with `status` when given. Stage "none" means no such deal. With
    offer None, a stage or status means "has a deal, any offer, at it", and
    "none" means no deal at all."""
    alias, column = _owner(alias, column)
    base = f"SELECT 1 FROM deals x WHERE x.{column} = {alias}.id AND x.deleted_at IS NULL"
    if offer:
        base += f" AND x.offer_id = {offer_id_sql(f'{alias}.workspace_id', offer)}"
    conditions, params = [], []
    if stage == "none":
        return [f"NOT EXISTS ({base})"], []
    if (offer and only_pitched) or stage or status:
        clause = base
        if stage:
            clause += " AND x.pipeline_stage = %s"
            params.append(stage)
        if status:
            clause += " AND x.status = %s"
            params.append(status)
        conditions.append(f"EXISTS ({clause})")
    return conditions, params


def deal_sort_sql(alias: str, column: str, offer: str | None, field: str) -> str:
    """Sort key for a deal field (pipeline_stage, status, next_step_date): that
    offer's value, or across every offer the values in offer order."""
    alias, column = _owner(alias, column)
    if field not in ("pipeline_stage", "status", "next_step_date"):
        raise ValueError(f"not a sortable deal field: {field!r}")
    only = f"AND x.offer_id = {offer_id_sql(f'{alias}.workspace_id', offer)}" if offer else ""
    if field == "next_step_date":  # the soonest one
        return (f"(SELECT MIN(x.next_step_date) FROM deals x WHERE x.{column} = {alias}.id "
                f"AND x.deleted_at IS NULL {only})")
    return (f"(SELECT string_agg(x.{field}, ',' ORDER BY o.sort_order, o.id) FROM deals x "
            f"JOIN offers o ON o.id = x.offer_id WHERE x.{column} = {alias}.id AND x.deleted_at IS NULL {only})")


def stage_and_status_counts(cur, table: str, alias: str, column: str, offer: str | None,
                            workspace_id: int | None) -> tuple[dict, dict]:
    """How many live deals sit at each stage and each status — one offer's, or
    every offer's — for the filter dropdowns. Returns ({stage: n}, {status: n})
    over the whole vocabulary, zeros included."""
    from gcrm.organization_state import STATUSES
    alias, column = _owner(alias, column)
    if table not in ("contacts", "people"):
        raise ValueError(f"not an owner table: {table!r}")
    only = f"AND x.offer_id = {offer_id_sql(f'{alias}.workspace_id', offer)}" if offer else ""
    scope = f"AND {alias}.workspace_id = %s" if workspace_id is not None else ""
    cur.execute(
        f"SELECT x.pipeline_stage, x.status, COUNT(*) AS cnt FROM {table} {alias} "
        f"JOIN deals x ON x.{column} = {alias}.id AND x.deleted_at IS NULL {only} "
        f"WHERE {alias}.deleted_at IS NULL {scope} GROUP BY 1, 2",
        [workspace_id] if workspace_id is not None else [],
    )
    stages, statuses = dict.fromkeys(PIPELINE_STAGES, 0), dict.fromkeys(STATUSES, 0)
    for row in cur.fetchall():
        if row["pipeline_stage"] in stages:
            stages[row["pipeline_stage"]] += row["cnt"]
        if row["status"] in statuses:
            statuses[row["status"]] += row["cnt"]
    return stages, statuses


def offer_slug_for(cur, offer_id: int | None) -> str:
    """The slug of an offer by id — Consulting for a record from before offers."""
    if offer_id is None:
        return CONSULTING
    cur.execute("SELECT slug FROM offers WHERE id = %s", (offer_id,))
    row = cur.fetchone()
    return row["slug"] if row else CONSULTING
