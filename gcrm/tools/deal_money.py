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
import uuid
from datetime import date, timedelta
from decimal import Decimal

from gcrm.db.connection import db, serialize_row
from gcrm.sale_series import (
    amount_and_hours,
    attach_contract_summaries,
    due_dates,
    monthly_due_day,
    rate_of,
    split_amount,
    split_hours,
)
from gcrm.sale_status import FIRM_PIPELINE_STATUSES, checked_sale_status, collected_day
from gcrm.tools.db_audit import log_audit
from gcrm.tools.deal_records import get_deal


def rate_text(amount, hours) -> str | None:
    rate = rate_of(amount, hours)
    return None if rate is None else str(rate)


def _money(amount) -> Decimal:
    value = Decimal(str(amount)).quantize(Decimal("0.01"))
    if value <= 0:
        raise ValueError("amount must be more than 0")
    return value


# --- One-off sales -----------------------------------------------------------

def insert_sale_payments(cur, workspace_id: int, deal_id: int, total: Decimal, won_on: date, description: str,
                         status: str, expected_on: date | None, collected_on: date | None,
                         months: int = 1, hours: Decimal | None = None) -> list[int]:
    """Insert one sale (months = 1) or a contract's monthly payments (months 2 to 60) on a
    deal, inside the caller's transaction, and return the new ids in payment order. A
    schedule needs the first due day, and starts as expected, booked or contracted: each
    payment is marked received when it arrives. `hours` (the whole sale's) is split over the payments
    like the money. Nothing is inserted when anything is refused."""
    text = (description or "").strip()[:500] or None
    if months == 1:
        parts, dues, series, hour_parts = [total], [expected_on], None, [hours]
        collected = [collected_day(status, collected_on, won_on)]
    else:
        if status == "collected":
            raise ValueError("a payment schedule starts as expected, booked or contracted; "
                             "mark each payment received as it arrives")
        if expected_on is None:
            raise ValueError("a payment schedule needs the day the first payment is due")
        dues, parts = due_dates(expected_on, months), split_amount(total, months)
        series, collected, hour_parts = str(uuid.uuid4()), [None] * months, split_hours(hours, months)
    ids = []
    for part, (amount, due, got, worked) in enumerate(zip(parts, dues, collected, hour_parts), start=1):
        cur.execute(
            "INSERT INTO sales (workspace_id, deal_id, amount_eur, won_on, description, status, expected_on, "
            "collected_on, series_id, series_part, series_total, hours) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::uuid, %s, %s, %s) RETURNING id",
            (workspace_id, deal_id, amount, won_on, text, status, due, got, series,
             part if series else None, months if series else None, worked),
        )
        ids.append(cur.fetchone()["id"])
    return ids


def add_deal_sale(deal_id: int, amount_eur, won_on: date, description: str = "",
                  workspace_id: int | None = None, status: str | None = None,
                  expected_on: date | None = None, collected_on: date | None = None,
                  months: int = 1, hours=None, rate=None) -> int:
    """Record a sale on a deal of an organization or person, or — with `months` 2 to 60 —
    a contract paid in that many monthly payments, the first due on `expected_on`. `status`
    defaults to collected (what every sale was before statuses). Returns the (first) sale's
    id. Raises DealNotFound, or ValueError for an amount not above 0, an unknown status or a
    schedule that cannot be made. `hours` is the work in the whole sale; with `rate` per hour and no
    amount, hours x rate is the amount."""
    amount, hours = amount_and_hours(amount_eur, hours, rate)
    status = checked_sale_status(status)
    with db() as conn:
        cur = conn.cursor()
        get_deal(cur, deal_id, workspace_id)
        cur.execute("SELECT workspace_id FROM deals WHERE id = %s", (deal_id,))
        ids = insert_sale_payments(cur, cur.fetchone()["workspace_id"], deal_id, amount, won_on, description, status,
                                   expected_on, collected_on, months, hours)
    log_audit(None, None, "sale.added", f"deal:{deal_id}",
              f"{amount} EUR on {won_on} ({status}" + (f", {months} payments)" if months > 1 else ")"))
    return ids[0]


OPEN_SALE_STATUSES = ("expected", "booked", "contracted")      # not received and not cancelled: they still have a due day


def set_sale_due_day(deal_id: int, sale_id: int, due_on: date, workspace_id: int | None = None) -> int:
    """Set or change the day a sale of this deal is due. For a payment of a monthly contract the payments
    after it follow monthly from the new day (the same day of the month, clipped in a short month, or the
    last day of each month when the new day is the last day of its month); the ones before it, and any
    already received, stay as they are. A received or cancelled sale keeps its day.
    Returns how many sales changed: 0 when the deal has no such open sale. Raises DealNotFound."""
    with db() as conn:
        cur = conn.cursor()
        get_deal(cur, deal_id, workspace_id)
        cur.execute("SELECT id, status, series_id::text AS series, series_part FROM sales "
                    "WHERE id = %s AND deal_id = %s AND deleted_at IS NULL FOR UPDATE", (sale_id, deal_id))
        sale = cur.fetchone()
        if sale is None or sale["status"] not in OPEN_SALE_STATUSES:
            return 0
        if sale["series"] is None:
            changes = [(sale["id"], due_on)]
        else:
            cur.execute("SELECT id, series_part FROM sales WHERE deal_id = %s AND series_id = %s::uuid AND deleted_at IS NULL "
                        "AND series_part >= %s AND status IN ('expected', 'booked', 'contracted') ORDER BY series_part FOR UPDATE",
                        (deal_id, sale["series"], sale["series_part"]))
            changes = [(row["id"], monthly_due_day(due_on, row["series_part"] - sale["series_part"])) for row in cur.fetchall()]
        for changed_id, day in changes:
            cur.execute("UPDATE sales SET expected_on = %s WHERE id = %s", (day, changed_id))
    log_audit(None, None, "sale.due_day", f"deal:{deal_id}", f"{sale_id} -> {due_on} ({len(changes)})")
    return len(changes)


def set_series_status(deal_id: int, series_id: str, status: str, workspace_id: int | None = None) -> int:
    """Move a contract's payments that are not yet received to `status` (expected, booked,
    contracted, or cancelled — and back again, to undo a slip). Received payments stay
    received. Returns how many payments changed; 0 when this deal has no such contract.
    Raises DealNotFound, or ValueError for an unknown status or for collected."""
    status = checked_sale_status(status)
    if status == "collected":
        raise ValueError("mark each payment received as it arrives, not the whole contract at once")
    with db() as conn:
        cur = conn.cursor()
        get_deal(cur, deal_id, workspace_id)
        cur.execute("UPDATE sales SET status = %s, collected_on = NULL WHERE deal_id = %s AND series_id = %s::uuid "
                    "AND deleted_at IS NULL AND status <> 'collected'", (status, deal_id, str(series_id)))
        changed = cur.rowcount
    if changed:
        log_audit(None, None, "sale.series_status", f"deal:{deal_id}", f"{series_id} -> {status} ({changed})")
    return changed


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
    (booked and contracted), expected_total} and subscriptions {rows, running} — `running` is the
    row in force today, or None."""
    today = today or date.today()
    money = {deal_id: {"sales_total": Decimal("0"), "pipeline_total": Decimal("0"), "expected_total": Decimal("0"), "sales": [], "subscriptions": [], "running": None}
             for deal_id in deal_ids}
    if not deal_ids:
        return money
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, deal_id, amount_eur, won_on, description, status, expected_on, collected_on, "
            "series_id::text AS series_id, series_part, series_total, hours FROM sales "
            "WHERE deal_id = ANY(%s) AND deleted_at IS NULL "
            "ORDER BY won_on DESC, COALESCE(series_id::text, ''), series_part, id DESC",
            (list(deal_ids),),
        )
        for row in cur.fetchall():
            entry = money[row["deal_id"]]
            entry["sales"].append({**serialize_row(dict(row)), "rate_eur": rate_text(row["amount_eur"], row["hours"])})
            if row["status"] == "collected":
                entry["sales_total"] += row["amount_eur"]
            elif row["status"] in FIRM_PIPELINE_STATUSES:
                entry["pipeline_total"] += row["amount_eur"]
            elif row["status"] == "expected":
                entry["expected_total"] += row["amount_eur"]
        for entry in money.values():
            attach_contract_summaries(entry["sales"])
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
