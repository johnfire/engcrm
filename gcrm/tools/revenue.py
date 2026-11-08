"""Revenue by sale status: per organization (as SQL columns for the list) and for the
whole business (the strip above it).

Statuses are gcrm/sale_status.py's. "Total" is everything still alive or paid —
expected + booked + contracted + collected — and leaves cancelled out, because a sale that
fell through is not revenue; cancelled is shown beside it, never added to it.
"""
from decimal import Decimal

from gcrm.db.connection import db
from gcrm.sale_status import SALE_STATUSES
from gcrm.tools.db_deals import offer_id_sql

TOTAL_STATUSES = ("expected", "booked", "contracted", "collected")


OWNER_COLUMNS = {"organization": "contact_id", "person": "person_id"}


def revenue_sum_sql(owner_alias: str, statuses: tuple[str, ...], offer: str | None,
                    owner_column: str = "contact_id") -> str:
    """A scalar subquery: the € of this organization's (or person's, with owner_column
    "person_id") live sales in the given statuses, 0 when none — `owner_alias`.id is the owner.
    Limited to one offer's deals when `offer` is given. Statuses and the column are checked
    against fixed lists, so nothing typed ever reaches the SQL."""
    unknown = set(statuses) - set(SALE_STATUSES)
    if unknown:
        raise ValueError(f"unknown sale status {sorted(unknown)}")
    if owner_column not in OWNER_COLUMNS.values():
        raise ValueError(f"unknown owner column {owner_column!r}")
    listed = ", ".join(f"'{status}'" for status in statuses)
    only = f" AND d.offer_id = {offer_id_sql(f'{owner_alias}.workspace_id', offer)}" if offer else ""
    return ("(SELECT COALESCE(SUM(s.amount_eur), 0) FROM sales s JOIN deals d ON d.id = s.deal_id "
            f"WHERE d.{owner_column} = {owner_alias}.id AND s.deleted_at IS NULL AND d.deleted_at IS NULL "
            f"AND s.status IN ({listed}){only})")


def revenue_columns_sql(owner_alias: str, offer: str | None) -> str:
    """The SELECT-list columns rev_expected … rev_cancelled and rev_total for the list."""
    parts = [f"{revenue_sum_sql(owner_alias, (status,), offer)} AS rev_{status}" for status in SALE_STATUSES]
    parts.append(f"{revenue_sum_sql(owner_alias, TOTAL_STATUSES, offer)} AS rev_total")
    return ",\n                ".join(parts)


def revenue_sort_sql(owner_alias: str, which: str, offer: str | None) -> str:
    """ORDER BY expression for 'revenue_collected' or 'revenue_total'."""
    statuses = ("collected",) if which == "revenue_collected" else TOTAL_STATUSES
    return revenue_sum_sql(owner_alias, statuses, offer)


def live_sales_sql(workspace_id: int, offer: str | None) -> tuple[str, list]:
    """The FROM ... WHERE for a workspace's live sales, organizations' and people's alike: the
    sale, its deal and its owner are not deleted, limited to one offer's deals when `offer` is given.
    Aliases: s sale, d deal, c organization, p person. Append further conditions with AND.
    Returns (sql, params). One definition, so every figure on every page counts the same sales."""
    only = f" AND d.offer_id = {offer_id_sql('%s', offer)}" if offer else ""
    sql = ("FROM sales s JOIN deals d ON d.id = s.deal_id AND d.deleted_at IS NULL "
           "LEFT JOIN contacts c ON c.id = d.contact_id LEFT JOIN people p ON p.id = d.person_id "
           f"WHERE s.workspace_id = %s AND s.deleted_at IS NULL AND COALESCE(c.deleted_at, p.deleted_at) IS NULL{only}")
    return sql, [workspace_id] + ([workspace_id] if offer else [])


def business_revenue(workspace_id: int | None, offer: str | None = None) -> dict:
    """{status: {eur, count}} for every sale of the workspace — organizations' and people's —
    plus "total" (without cancelled). Deleted owners and sales are left out."""
    with db() as conn:
        cur = conn.cursor()
        if workspace_id is None:
            cur.execute("SELECT id FROM workspaces WHERE slug = 'default'")
            workspace_id = cur.fetchone()["id"]
        scope, params = live_sales_sql(workspace_id, offer)
        cur.execute(
            "SELECT s.status, COALESCE(SUM(s.amount_eur), 0) AS eur, COUNT(*) AS n " + scope + " GROUP BY s.status",
            params,
        )
        found = {row["status"]: row for row in cur.fetchall()}
    totals = {status: {"eur": Decimal(found[status]["eur"]) if status in found else Decimal("0"),
                       "count": found[status]["n"] if status in found else 0} for status in SALE_STATUSES}
    totals["total"] = sum((totals[status]["eur"] for status in TOTAL_STATUSES), Decimal("0"))
    return totals


def total_value_sql(owner_alias: str, owner_column: str, offer: str | None) -> str:
    """TV: a scalar subquery with everything the owner is worth in sales that has not fallen
    through — expected + booked + contracted + collected."""
    return revenue_sum_sql(owner_alias, TOTAL_STATUSES, offer, owner_column)


def owner_total_value(owner: str, owner_id: int) -> dict:
    """{status: €, "total": €} for one organization or person (every offer), run inside the
    workspace's scope: another workspace's record simply has no sales to add up."""
    if owner not in OWNER_COLUMNS:
        raise ValueError(f"unknown owner {owner!r}")
    column = OWNER_COLUMNS[owner]
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT s.status, COALESCE(SUM(s.amount_eur), 0) AS eur FROM sales s JOIN deals d ON d.id = s.deal_id "
            f"WHERE d.{column} = %s AND s.deleted_at IS NULL AND d.deleted_at IS NULL GROUP BY s.status",
            (owner_id,),
        )
        found = {row["status"]: Decimal(row["eur"]) for row in cur.fetchall()}
    result = {status: found.get(status, Decimal("0")) for status in SALE_STATUSES}
    result["total"] = sum((result[status] for status in TOTAL_STATUSES), Decimal("0"))
    return result
