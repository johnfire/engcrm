"""Contracts in the database: the list, one contract with its payments and links, and every change to one.

A contract holds no money of its own: its figures are worked out from its live payments (gcrm/contract_math.py).
Every function filters the workspace itself and sees only live contracts on a live deal of a live owner, the same
conditions the Forecast counts sales under, so another workspace's or a deleted contract is simply not found
(ContractNotFound). Each change writes its audit event."""
from datetime import date
from decimal import Decimal, InvalidOperation

from gcrm.contract_input import (
    ContractInputError,
    checked_assignment,
    checked_link,
    checked_title,
)
from gcrm.contract_kinds import checked_kind
from gcrm.contract_math import contract_summary
from gcrm.db.connection import db, serialize_row
from gcrm.sale_series import attach_contract_summaries
from gcrm.sale_status import checked_sale_status
from gcrm.tools.db_audit import log_audit
from gcrm.tools.db_deals import offer_id_sql
from gcrm.tools.deal_money import insert_sale_payments, rate_text

MAX_LINKS = 50


class ContractNotFound(Exception):
    """No such contract (or link) in this workspace: missing, deleted, or another workspace's."""


# --- the list -----------------------------------------------------------------

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


# --- one contract ---------------------------------------------------------------

_VISIBLE = (
    "SELECT k.id, k.workspace_id, k.deal_id, k.title, k.kind, k.assignment, k.contact_person_id, k.created_at, "
    "k.updated_at, o.slug AS offer_slug, o.name AS offer_name, d.contact_id AS organization_id, d.person_id, "
    "COALESCE(c.name, p.name) AS owner_name "
    "FROM contracts k JOIN deals d ON d.id = k.deal_id AND d.deleted_at IS NULL JOIN offers o ON o.id = d.offer_id "
    "LEFT JOIN contacts c ON c.id = d.contact_id LEFT JOIN people p ON p.id = d.person_id "
    "WHERE k.id = %s AND k.workspace_id = %s AND d.workspace_id = %s AND k.deleted_at IS NULL "
    "AND COALESCE(c.deleted_at, p.deleted_at) IS NULL"
)


def _load(cur, contract_id: int, workspace_id: int, lock: bool = False) -> dict:
    """The contract as `get_contract` may show it, or ContractNotFound. `lock` holds the row until the
    transaction ends, so two changes to one contract (links in particular) do not interleave."""
    cur.execute(_VISIBLE + (" FOR UPDATE OF k" if lock else ""), (contract_id, workspace_id, workspace_id))
    row = cur.fetchone()
    if row is None:
        raise ContractNotFound(str(contract_id))
    return dict(row)


def _contact_candidates(cur, workspace_id: int, contract: dict) -> list[dict]:
    """The people who may be a contract's contact: live people who work at the deal's organization, or, for a deal
    that belongs to a person, that person alone. The one rule for both the picker and the check (row security only
    knows workspaces, so this lives here)."""
    if contract["organization_id"] is not None:
        cur.execute("SELECT id, name FROM people WHERE workspace_id = %s AND contact_id = %s AND deleted_at IS NULL "
                    "ORDER BY name, id", (workspace_id, contract["organization_id"]))
    else:
        cur.execute("SELECT id, name FROM people WHERE workspace_id = %s AND id = %s AND deleted_at IS NULL",
                    (workspace_id, contract["person_id"]))
    return [dict(row) for row in cur.fetchall()]


def get_contract(contract_id: int, workspace_id: int) -> dict:
    """One contract for its page: its fields, owner and offer, `contact_options` (who may be the contact person) and
    `contact_person` (the one chosen, if still allowed), its `links` in order, its live `payments` (shaped for the
    sale rows, with each payment series' summary) and the `summary` worked out from them. ContractNotFound."""
    with db() as conn:
        cur = conn.cursor()
        contract = _load(cur, contract_id, workspace_id)
        options = _contact_candidates(cur, workspace_id, contract)
        cur.execute("SELECT id, label, url, sort_order FROM contract_links WHERE contract_id = %s AND workspace_id = %s "
                    "ORDER BY sort_order, id", (contract_id, workspace_id))
        links = [dict(row) for row in cur.fetchall()]
        cur.execute(
            "SELECT id, deal_id, amount_eur, won_on, description, status, expected_on, collected_on, "
            "series_id::text AS series_id, series_part, series_total, hours, work_from, work_to FROM sales "
            "WHERE contract_id = %s AND workspace_id = %s AND deleted_at IS NULL "
            "ORDER BY won_on, COALESCE(series_id::text, ''), series_part, id", (contract_id, workspace_id))
        rows = cur.fetchall()
    summary = contract_summary([dict(row) for row in rows])
    payments = attach_contract_summaries([{**serialize_row(dict(row)), "rate_eur": rate_text(row["amount_eur"], row["hours"])}
                                          for row in rows])
    return {**contract, "contact_options": options,
            "contact_person": next((p for p in options if p["id"] == contract["contact_person_id"]), None),
            "links": links, "payments": payments, "summary": summary}


# --- changes ----------------------------------------------------------------------

def update_contract(contract_id: int, workspace_id: int, title, kind, assignment, contact_person_id: int | None) -> None:
    """Change a contract's title, kind, assignment and contact person (None: nobody). ContractInputError for a bad
    entry (including a contact person who does not work at the deal's organization, or, for a person's deal, is
    not that person); ContractNotFound."""
    title, kind, assignment = checked_title(title), checked_kind(kind), checked_assignment(assignment)
    with db() as conn:
        cur = conn.cursor()
        contract = _load(cur, contract_id, workspace_id, lock=True)
        if contact_person_id is not None and contact_person_id not in {p["id"] for p in _contact_candidates(cur, workspace_id, contract)}:
            raise ContractInputError("the contact person must work at the customer of this contract",
                                     "contractPage.error.contact")
        changed = [name for name, old, new in (("title", contract["title"], title), ("kind", contract["kind"], kind),
                                               ("assignment", contract["assignment"], assignment),
                                               ("contact", contract["contact_person_id"], contact_person_id)) if old != new]
        cur.execute("UPDATE contracts SET title = %s, kind = %s, assignment = %s, contact_person_id = %s, updated_at = NOW() "
                    "WHERE id = %s", (title, kind, assignment, contact_person_id, contract_id))
    log_audit(None, None, "contract.edited", f"contract:{contract_id}", ", ".join(changed) or "no change")


def delete_contract(contract_id: int, workspace_id: int) -> int:
    """Delete a contract and all its live payments together, in one transaction (soft delete: the rows stay,
    out of every page and the Forecast). Returns how many payments went. ContractNotFound."""
    with db() as conn:
        cur = conn.cursor()
        _load(cur, contract_id, workspace_id, lock=True)
        cur.execute("UPDATE sales SET deleted_at = NOW() WHERE contract_id = %s AND workspace_id = %s AND deleted_at IS NULL",
                    (contract_id, workspace_id))
        payments = cur.rowcount
        cur.execute("UPDATE contracts SET deleted_at = NOW(), updated_at = NOW() WHERE id = %s", (contract_id,))
    log_audit(None, None, "contract.deleted", f"contract:{contract_id}", f"{payments} payments")
    return payments


def add_link(contract_id: int, workspace_id: int, label, url) -> int:
    """Add a link at the end of a contract's links and return its id. ContractInputError for a bad label or
    address or too many links; ContractNotFound."""
    label, url = checked_link(label, url)
    with db() as conn:
        cur = conn.cursor()
        _load(cur, contract_id, workspace_id, lock=True)
        cur.execute("SELECT COUNT(*) AS n, COALESCE(MAX(sort_order), -1) AS last FROM contract_links WHERE contract_id = %s",
                    (contract_id,))
        found = cur.fetchone()
        if found["n"] >= MAX_LINKS:
            raise ContractInputError(f"a contract keeps at most {MAX_LINKS} links", "contractPage.error.tooManyLinks")
        cur.execute("INSERT INTO contract_links (workspace_id, contract_id, label, url, sort_order) "
                    "VALUES (%s, %s, %s, %s, %s) RETURNING id", (workspace_id, contract_id, label, url, found["last"] + 1))
        link_id = cur.fetchone()["id"]
    log_audit(None, None, "contract.link_added", f"contract:{contract_id}", f"link {link_id}")
    return link_id


def remove_link(contract_id: int, link_id: int, workspace_id: int) -> None:
    """Remove one of a contract's links. ContractNotFound when the contract, or the link on it, is not there."""
    with db() as conn:
        cur = conn.cursor()
        _load(cur, contract_id, workspace_id, lock=True)
        cur.execute("DELETE FROM contract_links WHERE id = %s AND contract_id = %s AND workspace_id = %s",
                    (link_id, contract_id, workspace_id))
        if cur.rowcount == 0:
            raise ContractNotFound(f"link {link_id}")
    log_audit(None, None, "contract.link_removed", f"contract:{contract_id}", f"link {link_id}")


def move_link(contract_id: int, link_id: int, direction: str, workspace_id: int) -> None:
    """Move a link one place "up" or "down" (the first cannot go up, the last cannot go down: nothing changes).
    The whole order is written again as 0, 1, 2 ..., so equal or gappy numbers from before never make the order
    unstable. ValueError for another direction; ContractNotFound."""
    if direction not in ("up", "down"):
        raise ValueError("move a link up or down")
    with db() as conn:
        cur = conn.cursor()
        _load(cur, contract_id, workspace_id, lock=True)
        cur.execute("SELECT id FROM contract_links WHERE contract_id = %s AND workspace_id = %s ORDER BY sort_order, id",
                    (contract_id, workspace_id))
        order = [row["id"] for row in cur.fetchall()]
        if link_id not in order:
            raise ContractNotFound(f"link {link_id}")
        index = order.index(link_id)
        other = index - 1 if direction == "up" else index + 1
        if 0 <= other < len(order):
            order[index], order[other] = order[other], order[index]
        for position, each in enumerate(order):
            cur.execute("UPDATE contract_links SET sort_order = %s WHERE id = %s AND sort_order <> %s", (position, each, position))
    log_audit(None, None, "contract.link_moved", f"contract:{contract_id}", f"link {link_id} {direction}")


def add_payment(contract_id: int, workspace_id: int, amount, due_on: date | None, status: str) -> int:
    """Add one payment to this contract (never a second contract) and return its id: `amount` euros, due on
    `due_on` (or no day yet), in `status`. A payment already collected counts as received today. ContractInputError for
    an amount that is not above 0; ValueError for an unknown status; ContractNotFound."""
    try:
        amount = Decimal(str(amount)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        amount = Decimal("0")
    if amount <= 0:
        raise ContractInputError("enter an amount above 0", "contractPage.error.payment")
    status = checked_sale_status(status)
    today = date.today()
    with db() as conn:
        cur = conn.cursor()
        contract = _load(cur, contract_id, workspace_id, lock=True)
        (payment_id,) = insert_sale_payments(cur, workspace_id, contract["deal_id"], amount, today, "", status, due_on, None,
                                             contract_id=contract_id)
    log_audit(None, None, "sale.added", f"deal:{contract['deal_id']}", f"{amount} EUR on {today} ({status})")
    return payment_id
