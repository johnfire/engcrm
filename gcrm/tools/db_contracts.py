"""Reading contracts: a contract and its live payments, for the Contracts pages."""
from gcrm.contract_kinds import checked_kind
from gcrm.contract_math import contract_summary
from gcrm.db.connection import db
from gcrm.tools.db_deals import offer_id_sql


def list_contracts(workspace_id: int, offer: str | None = None, kind: str | None = None) -> list[dict]:
    """Every live contract of the workspace (one offer's, one kind's, when given), each with its owner (the
    organization or person the deal belongs to), its offer and a `summary` worked out from its live payments
    (gcrm/contract_math.py). A contract whose payments are all deleted is still listed, empty. The
    contracts and payments counted are exactly those the Forecast counts (gcrm/tools/revenue.py): the deal and
    the owner not deleted. Ordered by id; grouping and sorting by timing is the caller's, which knows today.
    The workspace is filtered here, not left to row security alone. ValueError for an unknown kind."""
    if kind is not None:
        checked_kind(kind)
    only_offer = f" AND d.offer_id = {offer_id_sql('%s', offer)}" if offer else ""
    only_kind = " AND k.kind = %s" if kind else ""
    params = [workspace_id, workspace_id] + ([workspace_id] if offer else []) + ([kind] if kind else [])
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT k.id, k.deal_id, k.title, k.kind, o.slug AS offer_slug, o.name AS offer_name, "
            "c.id AS organization_id, p.id AS person_id, COALESCE(c.name, p.name) AS owner_name, "
            "s.amount_eur, s.hours, s.status, s.won_on, s.expected_on, s.collected_on, s.work_from, s.work_to "
            "FROM contracts k JOIN deals d ON d.id = k.deal_id AND d.deleted_at IS NULL "
            "JOIN offers o ON o.id = d.offer_id "
            "LEFT JOIN contacts c ON c.id = d.contact_id LEFT JOIN people p ON p.id = d.person_id "
            "LEFT JOIN sales s ON s.contract_id = k.id AND s.deleted_at IS NULL AND s.workspace_id = k.workspace_id "
            "WHERE k.workspace_id = %s AND d.workspace_id = %s AND k.deleted_at IS NULL "
            f"AND COALESCE(c.deleted_at, p.deleted_at) IS NULL{only_offer}{only_kind} "
            "ORDER BY k.id, s.id",
            params,
        )
        rows = cur.fetchall()
    contracts: dict[int, dict] = {}
    payments: dict[int, list[dict]] = {}
    for row in rows:
        if row["id"] not in contracts:
            contracts[row["id"]] = {key: row[key] for key in ("id", "deal_id", "title", "kind", "offer_slug", "offer_name",
                                                              "organization_id", "person_id", "owner_name")}
            payments[row["id"]] = []
        if row["status"] is not None:                       # the LEFT JOIN found a live payment
            payments[row["id"]].append({key: row[key] for key in
                                        ("amount_eur", "hours", "status", "won_on", "expected_on", "collected_on",
                                         "work_from", "work_to")})
    for contract_id, contract in contracts.items():
        contract["summary"] = contract_summary(payments[contract_id])
    return list(contracts.values())
