"""What a deal earns: one-off sales and monthly subscriptions.

A sale belongs to a deal of an organization or of a person (a consultant you
sell to). It has a status (gcrm/sale_status.py): only collected ones are won. A subscription belongs to any deal and runs from
`started_on` through `ended_on` (the last day paid for), or open-ended while it
runs. A deal has at most one running subscription: starting a new one ends the
running one the day before — that is how a price change is recorded, so past
months keep their real amount.

Subscription revenue is *calculated* from these rows (€/month × the days it ran
÷ the days in that month), never checked against payments.
"""
from datetime import date, timedelta
from decimal import Decimal

from gcrm.db.connection import db, serialize_row
from gcrm.sale_status import PIPELINE_SALE_STATUSES, checked_sale_status, collected_day
from gcrm.tools.db_audit import log_audit
from gcrm.tools.deal_records import get_deal


def _money(amount) -> Decimal:
    value = Decimal(str(amount)).quantize(Decimal("0.01"))
    if value <= 0:
        raise ValueError("amount must be more than 0")
    return value


# --- One-off sales -----------------------------------------------------------

def add_deal_sale(deal_id: int, amount_eur, won_on: date, description: str = "",
                  workspace_id: int | None = None, status: str | None = None,
                  expected_on: date | None = None, collected_on: date | None = None) -> int:
    """Record a one-off sale on a deal of an organization or person. `status`
    defaults to collected (what every sale was before statuses). Raises
    DealNotFound, or ValueError for an amount not above 0 or an unknown status."""
    amount = _money(amount_eur)
    status = checked_sale_status(status)
    collected = collected_day(status, collected_on, won_on)
    with db() as conn:
        cur = conn.cursor()
        get_deal(cur, deal_id, workspace_id)
        cur.execute(
            "INSERT INTO sales (workspace_id, deal_id, amount_eur, won_on, description, status, expected_on, "
            "collected_on) SELECT workspace_id, id, %s, %s, %s, %s, %s, %s FROM deals WHERE id = %s RETURNING id",
            (amount, won_on, (description or "").strip()[:500] or None, status, expected_on, collected, deal_id),
        )
        sale_id = cur.fetchone()["id"]
    log_audit(None, None, "sale.added", f"deal:{deal_id}", f"{amount} EUR on {won_on} ({status})")
    return sale_id


def set_sale_status(deal_id: int, sale_id: int, status: str, collected_on: date | None = None,
                    workspace_id: int | None = None) -> bool:
    """Move a sale of this deal along (or back, if it was a slip): booked →
    contracted → collected, or cancelled. Collecting takes the day the money came
    in (today when not given); leaving collected clears it. False if the deal has
    no such sale. Raises DealNotFound, or ValueError for an unknown status."""
    status = checked_sale_status(status)
    with db() as conn:
        cur = conn.cursor()
        get_deal(cur, deal_id, workspace_id)
        cur.execute(
            "UPDATE sales SET status = %s, collected_on = %s WHERE id = %s AND deal_id = %s "
            "AND deleted_at IS NULL",
            (status, collected_day(status, collected_on, date.today()), sale_id, deal_id),
        )
        changed = cur.rowcount > 0
    if changed:
        log_audit(None, None, "sale.status", f"deal:{deal_id}", f"{sale_id} -> {status}")
    return changed


def delete_deal_sale(deal_id: int, sale_id: int, workspace_id: int | None = None) -> bool:
    """Remove a mistyped sale of this deal (soft delete). Raises DealNotFound."""
    with db() as conn:
        cur = conn.cursor()
        get_deal(cur, deal_id, workspace_id)
        cur.execute("UPDATE sales SET deleted_at = NOW() WHERE id = %s AND deal_id = %s AND deleted_at IS NULL",
                    (sale_id, deal_id))
        deleted = cur.rowcount > 0
    if deleted:
        log_audit(None, None, "sale.deleted", f"deal:{deal_id}", str(sale_id))
    return deleted


# --- Subscriptions -----------------------------------------------------------

def start_subscription(deal_id: int, amount_eur_month, started_on: date, note: str = "",
                       workspace_id: int | None = None) -> int:
    """Start (or re-price) the deal's subscription from `started_on`. A running
    one ends the day before; one starting on or after that day is refused, as
    the two would overlap. Raises DealNotFound or ValueError."""
    amount = _money(amount_eur_month)
    with db() as conn:
        cur = conn.cursor()
        get_deal(cur, deal_id, workspace_id)
        cur.execute(
            "SELECT id, started_on FROM subscriptions WHERE deal_id = %s AND deleted_at IS NULL "
            "AND (ended_on IS NULL OR ended_on >= %s) FOR UPDATE",
            (deal_id, started_on),
        )
        for running in cur.fetchall():
            if running["started_on"] >= started_on:
                raise ValueError("a subscription already starts on or after that day")
            cur.execute("UPDATE subscriptions SET ended_on = %s WHERE id = %s",
                        (started_on - timedelta(days=1), running["id"]))
        cur.execute(
            "INSERT INTO subscriptions (workspace_id, deal_id, amount_eur_month, started_on, note) "
            "SELECT workspace_id, id, %s, %s, %s FROM deals WHERE id = %s RETURNING id",
            (amount, started_on, (note or "").strip()[:500] or None, deal_id),
        )
        subscription_id = cur.fetchone()["id"]
    log_audit(None, None, "subscription.started", f"deal:{deal_id}", f"{amount} EUR/month from {started_on}")
    return subscription_id


def end_subscription(deal_id: int, ended_on: date, workspace_id: int | None = None) -> bool:
    """End the deal's running subscription on `ended_on` (the last day paid for).
    False when nothing is running. ValueError for a day before it started."""
    with db() as conn:
        cur = conn.cursor()
        get_deal(cur, deal_id, workspace_id)
        cur.execute(
            "SELECT id, started_on FROM subscriptions WHERE deal_id = %s AND deleted_at IS NULL "
            "AND ended_on IS NULL FOR UPDATE",
            (deal_id,),
        )
        running = cur.fetchone()
        if running is None:
            return False
        if ended_on < running["started_on"]:
            raise ValueError("a subscription cannot end before it started")
        cur.execute("UPDATE subscriptions SET ended_on = %s WHERE id = %s", (ended_on, running["id"]))
    log_audit(None, None, "subscription.ended", f"deal:{deal_id}", f"on {ended_on}")
    return True


def delete_subscription(deal_id: int, subscription_id: int, workspace_id: int | None = None) -> bool:
    """Remove a mistyped subscription row (soft delete)."""
    with db() as conn:
        cur = conn.cursor()
        get_deal(cur, deal_id, workspace_id)
        cur.execute("UPDATE subscriptions SET deleted_at = NOW() WHERE id = %s AND deal_id = %s "
                    "AND deleted_at IS NULL", (subscription_id, deal_id))
        deleted = cur.rowcount > 0
    if deleted:
        log_audit(None, None, "subscription.deleted", f"deal:{deal_id}", str(subscription_id))
    return deleted


# --- What the Deals panel shows ----------------------------------------------

def deal_money(deal_ids: list[int], today: date | None = None) -> dict[int, dict]:
    """Per deal: one-off sales {rows, sales_total (collected only), pipeline_total
    (booked and contracted)} and subscriptions {rows, running} — `running` is the
    row in force today, or None."""
    today = today or date.today()
    money = {deal_id: {"sales_total": Decimal("0"), "pipeline_total": Decimal("0"), "sales": [], "subscriptions": [], "running": None}
             for deal_id in deal_ids}
    if not deal_ids:
        return money
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, deal_id, amount_eur, won_on, description, status, expected_on, collected_on FROM sales "
            "WHERE deal_id = ANY(%s) AND deleted_at IS NULL ORDER BY won_on DESC, id DESC",
            (list(deal_ids),),
        )
        for row in cur.fetchall():
            entry = money[row["deal_id"]]
            entry["sales"].append(serialize_row(dict(row)))
            if row["status"] == "collected":
                entry["sales_total"] += row["amount_eur"]
            elif row["status"] in PIPELINE_SALE_STATUSES:
                entry["pipeline_total"] += row["amount_eur"]
        cur.execute(
            "SELECT id, deal_id, amount_eur_month, started_on, ended_on, note FROM subscriptions "
            "WHERE deal_id = ANY(%s) AND deleted_at IS NULL ORDER BY started_on DESC, id DESC",
            (list(deal_ids),),
        )
        for row in cur.fetchall():
            entry = money[row["deal_id"]]
            if row["started_on"] <= today and (row["ended_on"] is None or row["ended_on"] >= today):
                entry["running"] = serialize_row(dict(row))
            entry["subscriptions"].append(serialize_row(dict(row)))
    return money
