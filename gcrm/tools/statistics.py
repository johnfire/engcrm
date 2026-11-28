"""Statistics: effort in, euros out. See docs/plans/2026-10-05-statistics-design.md.

Everything is scoped to one workspace and one period [start, end] (dates,
inclusive). Activities come from both organization and person logs, with person
activities counted towards the organization the person works at.
"""
from datetime import date, timedelta
from decimal import Decimal

from gcrm.activity_types import ACTIVITY_TYPES, DEFAULT_MINUTES, NOT_ACTIVITIES, type_case_sql
from gcrm.db.connection import db, serialize_row
from gcrm.organization_state import PIPELINE_STAGES
from gcrm.sale_series import amount_and_hours, attach_contract_summaries
from gcrm.sale_status import (
    LIVE_SALE_STATUSES,
    PIPELINE_SALE_STATUSES,
    SOLD_STATUSES,
    checked_sale_status,
)
from gcrm.tools.db_audit import log_audit
from gcrm.tools.db_deals import CONSULTING, offer_id_sql
from gcrm.tools.deal_money import insert_sale_payments, rate_text, retire_emptied_contracts

PERIODS = ("week", "month", "quarter", "year")
WORKING_STAGES = ("suspect", "nibble", "prospect", "opportunity")
STUCK_AFTER_DAYS = 28
STUCK_LIMIT = 25
_FORWARD_ORDER = [s for s in PIPELINE_STAGES if s not in ("not_now", "not_in_pipeline")]


# --- Periods -----------------------------------------------------------------

def period_bounds(period: str, today: date) -> tuple[date, date]:
    """The calendar week (Monday first), month, quarter or year containing `today`."""
    if period == "week":
        start = today - timedelta(days=today.weekday())
        return start, start + timedelta(days=6)
    if period == "month":
        start = today.replace(day=1)
    elif period == "quarter":
        start = date(today.year, 3 * ((today.month - 1) // 3) + 1, 1)
    elif period == "year":
        return date(today.year, 1, 1), date(today.year, 12, 31)
    else:
        raise ValueError(f"unknown period {period!r}")
    months = 1 if period == "month" else 3
    year, month = divmod(start.month - 1 + months, 12)
    return start, date(start.year + year, month + 1, 1) - timedelta(days=1)


def previous_period(start: date, end: date) -> tuple[date, date]:
    """The period of the same length just before [start, end]."""
    length = (end - start).days + 1
    return start - timedelta(days=length), start - timedelta(days=1)


# --- Default minutes ------------------------------------------------------------

def get_minute_defaults(workspace_id: int) -> dict[str, int]:
    """Minutes per activity type for this workspace, the built-in values filling gaps."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT activity_type, minutes FROM activity_minute_defaults WHERE workspace_id = %s",
            (workspace_id,),
        )
        stored = {row["activity_type"]: row["minutes"] for row in cur.fetchall()}
    return {kind: stored.get(kind, DEFAULT_MINUTES[kind]) for kind in ACTIVITY_TYPES}


def set_minute_defaults(workspace_id: int, minutes: dict[str, int]) -> None:
    """Store the default minutes for the given types (unknown types are ignored)."""
    with db() as conn:
        cur = conn.cursor()
        for kind, value in minutes.items():
            if kind not in ACTIVITY_TYPES:
                continue
            cur.execute(
                "INSERT INTO activity_minute_defaults (workspace_id, activity_type, minutes) "
                "VALUES (%s, %s, %s) ON CONFLICT (workspace_id, activity_type) "
                "DO UPDATE SET minutes = EXCLUDED.minutes",
                (workspace_id, kind, int(value)),
            )
    log_audit(None, None, "settings.activity_minutes", f"workspace:{workspace_id}",
              ",".join(f"{k}={v}" for k, v in sorted(minutes.items())))


# --- Sales ---------------------------------------------------------------------

def add_sale(workspace_id: int, contact_id: int, amount_eur: Decimal, won_on: date, description: str,
             deal_id: int | None = None, status: str | None = None, expected_on: date | None = None,
             collected_on: date | None = None, months: int = 1, hours=None, rate=None,
             work_from: date | None = None, work_to: date | None = None, title: str | None = None,
             kind: str = "other") -> int | None:
    """Record a sale on an organization of this workspace, for one of its deals
    (`deal_id`; its Consulting deal when not given), or — with `months` 2 to 60 — a contract
    paid in that many monthly payments, the first due on `expected_on`. `status` defaults to
    collected. Returns the (first) sale's id; None if there is no such organization, or no such
    live deal of it. Raises ValueError for an amount not above 0, an unknown status or a
    schedule that cannot be made. `hours` is the work in the whole sale; with `rate` per hour and no
    amount, hours x rate is the amount."""
    amount_eur, hours = amount_and_hours(amount_eur, hours, rate)
    status = checked_sale_status(status)
    which = "x.id = %s" if deal_id is not None else f"x.offer_id = {offer_id_sql('c.workspace_id', CONSULTING)}"
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT x.id FROM contacts c JOIN deals x ON x.contact_id = c.id "
            "WHERE c.id = %s AND c.workspace_id = %s AND c.deleted_at IS NULL AND x.deleted_at IS NULL "
            f"AND {which}",
            [contact_id, workspace_id, *([deal_id] if deal_id is not None else [])],
        )
        deal = cur.fetchone()
        if deal is None:
            return None
        ids = insert_sale_payments(cur, workspace_id, deal["id"], Decimal(amount_eur), won_on,
                                   description, status, expected_on, collected_on, months, hours, work_from, work_to,
                                   title=title, kind=kind)
    log_audit(None, None, "sale.added", f"contact:{contact_id}", f"{amount_eur} EUR on {won_on}")
    return ids[0]


def get_sales(contact_id: int) -> list[dict]:
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT s.id, s.deal_id, s.amount_eur, s.won_on, s.description, s.status, s.expected_on, s.collected_on, "
            "s.series_id::text AS series_id, s.series_part, s.series_total, s.hours, s.work_from, s.work_to, o.name AS offer FROM sales s "
            "JOIN deals d ON d.id = s.deal_id JOIN offers o ON o.id = d.offer_id "
            "WHERE d.contact_id = %s AND s.deleted_at IS NULL "
            "ORDER BY s.won_on DESC, COALESCE(s.series_id::text, ''), s.series_part, s.id DESC",
            (contact_id,),
        )
        return attach_contract_summaries([{**serialize_row(dict(row)), "rate_eur": rate_text(row["amount_eur"], row["hours"])}
                                          for row in cur.fetchall()])


def delete_sale(contact_id: int, sale_id: int) -> bool:
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE sales SET deleted_at = NOW() WHERE id = %s AND deleted_at IS NULL "
            "AND deal_id IN (SELECT id FROM deals WHERE contact_id = %s) RETURNING contract_id",
            (sale_id, contact_id),
        )
        gone = cur.fetchall()
        deleted = len(gone) > 0
        retire_emptied_contracts(cur, [row["contract_id"] for row in gone])
    if deleted:
        log_audit(None, None, "sale.deleted", f"contact:{contact_id}", str(sale_id))
    return deleted


# --- The numbers ---------------------------------------------------------------

def _offer_sql(workspace_id: int, offer: str) -> str:
    """The id of `offer` in this workspace, as SQL. The workspace id is the
    server's own integer, the slug is checked by offer_id_sql."""
    return offer_id_sql(str(int(workspace_id)), offer)


def activities_sql(defaults: dict[str, int], offer: str | None = None, workspace_id: int | None = None) -> tuple[str, list]:
    """A CTE `acts(day, kind, minutes, typed, contact_id)` over both activity logs of
    one workspace: inbound messages and next-step entries (on either log) are not
    work; a person's activities count towards their organization. With an
    `offer`, only activities logged as being about it."""
    values = ", ".join("(%s, %s)" for _ in defaults)
    excluded = ", ".join("%s" for _ in NOT_ACTIVITIES)
    plans = ", ".join(f"'{method}'" for method in NOT_ACTIVITIES)  # constants, never input
    only = f"WHERE raw.offer_id = {_offer_sql(workspace_id, offer)}" if offer else ""
    sql = f"""
        defaults(kind, minutes) AS (VALUES {values}),
        raw AS (
            SELECT i.interaction_date AS day, {type_case_sql('i.method')} AS kind,
                   i.duration_minutes AS typed, c.id AS contact_id, i.offer_id
              FROM interactions i JOIN contacts c ON c.id = i.contact_id
             WHERE i.deleted_at IS NULL AND c.workspace_id = %s
               AND COALESCE(i.direction, '') <> 'inbound'
               AND COALESCE(i.method, '') NOT IN ({plans})
            UNION ALL
            SELECT pi.occurred_at::date, {type_case_sql('pi.method')},
                   pi.duration_minutes, p.contact_id, pi.offer_id
              FROM people_interactions pi JOIN people p ON p.id = pi.person_id
             WHERE pi.deleted_at IS NULL AND p.deleted_at IS NULL AND p.workspace_id = %s
               AND COALESCE(pi.method, '') NOT IN ({excluded})
        ),
        acts AS (
            SELECT raw.day, raw.kind, raw.typed, raw.contact_id,
                   COALESCE(raw.typed, defaults.minutes, 0) AS minutes
              FROM raw LEFT JOIN defaults ON defaults.kind = raw.kind
             {only}
        )"""
    params = [x for kind, minutes in defaults.items() for x in (kind, minutes)]
    return sql, params


def _sales_offer(workspace_id: int, offer: str | None, column: str = "deal_id") -> str:
    return (f" AND {column} IN (SELECT id FROM deals WHERE offer_id = {_offer_sql(workspace_id, offer)})"
            if offer else "")


def subscription_revenue(cur, workspace_id: int, start: date, end: date, offer: str | None,
                         today: date) -> Decimal:
    """What the subscriptions earned in [start, end], up to `today`: €/month ×
    each day they ran ÷ the days in that day's month. Calculated, not paid."""
    last = min(end, today)
    if last < start:
        return Decimal("0")
    cur.execute(
        "SELECT COALESCE(SUM(s.amount_eur_month / EXTRACT(DAY FROM (date_trunc('month', d) "
        "+ interval '1 month' - interval '1 day'))), 0) AS revenue FROM subscriptions s "
        "CROSS JOIN LATERAL generate_series(GREATEST(s.started_on, %s::date), "
        "LEAST(COALESCE(s.ended_on, %s::date), %s::date), interval '1 day') AS d "
        f"WHERE s.workspace_id = %s AND s.deleted_at IS NULL{_sales_offer(workspace_id, offer, 's.deal_id')}",
        (start, last, last, workspace_id),
    )
    return Decimal(cur.fetchone()["revenue"]).quantize(Decimal("0.01"))


def _mrr_moves(cur, workspace_id: int, start: date, end: date, offer: str | None) -> dict:
    """New MRR (subscriptions starting with nothing running the day before on that
    deal) and lost MRR (ending with nothing starting the next day): a price
    change is neither."""
    scope = _sales_offer(workspace_id, offer, "s.deal_id")
    cur.execute(
        "SELECT "
        " COALESCE(SUM(s.amount_eur_month) FILTER (WHERE s.started_on BETWEEN %s AND %s AND NOT EXISTS ("
        "   SELECT 1 FROM subscriptions b WHERE b.deal_id = s.deal_id AND b.deleted_at IS NULL "
        "   AND b.ended_on = s.started_on - 1)), 0) AS new_mrr, "
        " COALESCE(SUM(s.amount_eur_month) FILTER (WHERE s.ended_on BETWEEN %s AND %s AND NOT EXISTS ("
        "   SELECT 1 FROM subscriptions a WHERE a.deal_id = s.deal_id AND a.deleted_at IS NULL "
        "   AND a.started_on = s.ended_on + 1)), 0) AS lost_mrr "
        f"FROM subscriptions s WHERE s.workspace_id = %s AND s.deleted_at IS NULL{scope}",
        (start, end, start, end, workspace_id),
    )
    row = cur.fetchone()
    return {"new_mrr": Decimal(row["new_mrr"]), "lost_mrr": Decimal(row["lost_mrr"])}


def mrr_now(cur, workspace_id: int, offer: str | None, today: date) -> dict:
    """The monthly recurring revenue running today, and how many deals pay it."""
    cur.execute(
        "SELECT COALESCE(SUM(s.amount_eur_month), 0) AS mrr, COUNT(DISTINCT s.deal_id) AS subscribers "
        "FROM subscriptions s WHERE s.workspace_id = %s AND s.deleted_at IS NULL AND s.started_on <= %s "
        f"AND (s.ended_on IS NULL OR s.ended_on >= %s){_sales_offer(workspace_id, offer, 's.deal_id')}",
        (workspace_id, today, today),
    )
    row = cur.fetchone()
    return {"mrr": Decimal(row["mrr"]), "subscribers": row["subscribers"]}


def _money_figures(cur, workspace_id: int, start: date, end: date, offer: str | None) -> dict:
    """Sold (booked, contracted or collected, by the day it was agreed), expected (the same
    rule), and collected (money in, by the day it came in). A contract is counted once, however
    many monthly payments it has."""
    cur.execute(
        "SELECT "
        " COALESCE(SUM(amount_eur) FILTER (WHERE status = ANY(%s) AND won_on BETWEEN %s AND %s), 0) AS sold_eur, "
        " COUNT(DISTINCT contract_id) FILTER (WHERE status = ANY(%s) AND won_on BETWEEN %s AND %s) AS sold_contracts, "
        " COALESCE(SUM(amount_eur) FILTER (WHERE status = 'expected' AND won_on BETWEEN %s AND %s), 0) AS expected_eur, "
        " COUNT(DISTINCT contract_id) FILTER (WHERE status = 'expected' AND won_on BETWEEN %s AND %s) AS expected_contracts, "
        " COALESCE(SUM(amount_eur) FILTER (WHERE status = 'collected' AND collected_on BETWEEN %s AND %s), 0) AS collected_eur "
        f"FROM sales WHERE workspace_id = %s AND deleted_at IS NULL{_sales_offer(workspace_id, offer)}",
        (list(SOLD_STATUSES), start, end, list(SOLD_STATUSES), start, end, start, end, start, end, start, end, workspace_id),
    )
    row = cur.fetchone()
    return {"sold_eur": Decimal(row["sold_eur"]), "sold_contracts": row["sold_contracts"],
            "expected_eur": Decimal(row["expected_eur"]), "expected_contracts": row["expected_contracts"],
            "collected_eur": Decimal(row["collected_eur"])}


def _summary(cur, acts_sql: str, acts_params: list, workspace_id: int, start: date, end: date,
             offer: str | None = None, today: date | None = None) -> dict:
    """The headline figures for one period, used for both the period and the one before."""
    today = today or date.today()
    cur.execute(
        f"WITH {acts_sql} SELECT kind, COUNT(*) AS n, SUM(minutes) AS minutes, "
        "COUNT(*) FILTER (WHERE typed IS NULL AND minutes > 0) AS estimated "
        "FROM acts WHERE day BETWEEN %s AND %s GROUP BY kind",
        acts_params + [workspace_id, workspace_id, *NOT_ACTIVITIES, start, end],
    )
    by_kind = {row["kind"]: dict(row) for row in cur.fetchall()}
    effort = {kind: {"count": by_kind.get(kind, {}).get("n", 0),
                     "minutes": int(by_kind.get(kind, {}).get("minutes") or 0),
                     "estimated": by_kind.get(kind, {}).get("estimated", 0)} for kind in ACTIVITY_TYPES}
    money = _money_figures(cur, workspace_id, start, end, offer)
    subscriptions = subscription_revenue(cur, workspace_id, start, end, offer, today)
    moves = _mrr_moves(cur, workspace_id, start, end, offer)
    cur.execute(
        "SELECT entity_type, from_stage, to_stage, COUNT(*) AS n FROM stage_changes "
        "WHERE workspace_id = %s AND changed_at::date BETWEEN %s AND %s "
        + (f"AND offer_id = {_offer_sql(workspace_id, offer)} " if offer else "")
        + "GROUP BY entity_type, from_stage, to_stage ORDER BY n DESC",
        (workspace_id, start, end),
    )
    changes = [{**dict(row), "direction": stage_direction(row["from_stage"], row["to_stage"])}
               for row in cur.fetchall()]
    cur.execute(
        "SELECT (SELECT COUNT(*) FROM contacts WHERE workspace_id = %s AND deleted_at IS NULL "
        "        AND created_at::date BETWEEN %s AND %s) AS organizations, "
        "       (SELECT COUNT(*) FROM people WHERE workspace_id = %s AND deleted_at IS NULL "
        "        AND created_at::date BETWEEN %s AND %s) AS people",
        (workspace_id, start, end, workspace_id, start, end),
    )
    new = cur.fetchone()
    activities = sum(e["count"] for kind, e in effort.items() if kind != "note")
    return {
        "effort": effort,
        "activities": activities,
        "minutes": sum(e["minutes"] for e in effort.values()),
        "estimated": sum(e["estimated"] for e in effort.values()),
        **money,
        "subscription_eur": subscriptions,
        "new_mrr": moves["new_mrr"],
        "lost_mrr": moves["lost_mrr"],
        "stage_changes": changes,
        "promotions": sum(c["n"] for c in changes if c["direction"] == "forward"),
        "new_organizations": new["organizations"],
        "new_people": new["people"],
    }


def stage_direction(from_stage: str | None, to_stage: str | None) -> str:
    """forward / back / dropped / other, along candidate → … → customer."""
    if to_stage == "not_in_pipeline":
        return "dropped"
    if to_stage == "not_now":
        return "back"  # stepped back; leaving it again is not a promotion, so "other"
    if from_stage in _FORWARD_ORDER and to_stage in _FORWARD_ORDER:
        return "forward" if _FORWARD_ORDER.index(to_stage) > _FORWARD_ORDER.index(from_stage) else "back"
    return "other"


def _new_by_source(cur, workspace_id: int, start: date, end: date) -> list[dict]:
    cur.execute(
        "SELECT 'organization' AS kind, COALESCE(NULLIF(source, ''), 'unknown') AS source, COUNT(*) AS n "
        "FROM contacts WHERE workspace_id = %s AND deleted_at IS NULL AND created_at::date BETWEEN %s AND %s "
        "GROUP BY 2 UNION ALL "
        "SELECT 'person', COALESCE(NULLIF(source, ''), 'unknown'), COUNT(*) FROM people "
        "WHERE workspace_id = %s AND deleted_at IS NULL AND created_at::date BETWEEN %s AND %s "
        "GROUP BY 2 ORDER BY 1, 3 DESC",
        (workspace_id, start, end, workspace_id, start, end),
    )
    return [dict(row) for row in cur.fetchall()]


def _stages_now(cur, workspace_id: int, offer: str | None) -> dict:
    only = f"AND d.offer_id = {_offer_sql(workspace_id, offer)} " if offer else ""
    cur.execute(
        "SELECT CASE WHEN d.contact_id IS NOT NULL THEN 'organization' ELSE 'person' END AS kind, "
        "d.pipeline_stage AS stage, COUNT(*) AS n FROM deals d "
        "LEFT JOIN contacts c ON c.id = d.contact_id LEFT JOIN people p ON p.id = d.person_id "
        "WHERE d.workspace_id = %s AND d.deleted_at IS NULL AND c.deleted_at IS NULL AND p.deleted_at IS NULL "
        f"{only}GROUP BY 1, 2",
        (workspace_id,),
    )
    stages = {"organization": {}, "person": {}}
    for row in cur.fetchall():
        stages[row["kind"]][row["stage"]] = row["n"]
    return stages


def stuck_deals(cur, workspace_id: int, offer: str | None, today: date) -> tuple[list[dict], int]:
    """Deals in a working stage whose latest sign of life is over STUCK_AFTER_DAYS ago: the latest of
    the last activity (inbound messages count, next-step entries do not), the day the deal was
    created and the day it entered its stage. An organization's deal is judged by the
    organization's log plus its people's; a person's deal by that person's log. Returns the
    STUCK_LIMIT oldest and how many there are in all."""
    plans = ", ".join(f"'{method}'" for method in NOT_ACTIVITIES)  # constants, never input
    only_deal = f"AND d.offer_id = {_offer_sql(workspace_id, offer)} " if offer else ""
    only_activity = f"AND a.offer_id = {_offer_sql(workspace_id, offer)} " if offer else ""
    cur.execute(
        f"""WITH activity AS (
            SELECT i.contact_id, NULL::int AS person_id, i.interaction_date AS day, i.offer_id
              FROM interactions i JOIN contacts c ON c.id = i.contact_id
             WHERE i.deleted_at IS NULL AND c.workspace_id = %s AND COALESCE(i.method, '') NOT IN ({plans})
            UNION ALL
            SELECT p.contact_id, pi.person_id, pi.occurred_at::date, pi.offer_id
              FROM people_interactions pi JOIN people p ON p.id = pi.person_id
             WHERE pi.deleted_at IS NULL AND p.deleted_at IS NULL AND p.workspace_id = %s
               AND COALESCE(pi.method, '') NOT IN ({plans})
        ), entered AS (
            SELECT deal_id, MAX(changed_at)::date AS day FROM stage_changes
             WHERE workspace_id = %s AND deal_id IS NOT NULL GROUP BY deal_id
        ), state AS (
            SELECT d.contact_id AS id, d.person_id, COALESCE(c.name, p.name) AS name, d.pipeline_stage,
                   o.name AS offer, d.created_at::date AS added_on,
                   (SELECT MAX(a.day) FROM activity a WHERE (a.contact_id = d.contact_id
                        OR (d.contact_id IS NULL AND a.person_id = d.person_id)) {only_activity}) AS last_day,
                   e.day AS entered_on
              FROM deals d JOIN offers o ON o.id = d.offer_id
              LEFT JOIN contacts c ON c.id = d.contact_id LEFT JOIN people p ON p.id = d.person_id
              LEFT JOIN entered e ON e.deal_id = d.id
             WHERE d.workspace_id = %s AND d.deleted_at IS NULL AND c.deleted_at IS NULL AND p.deleted_at IS NULL
               AND d.pipeline_stage = ANY(%s) {only_deal}
        ), judged AS (
            SELECT *, GREATEST(added_on, COALESCE(last_day, added_on), COALESCE(entered_on, added_on)) AS latest
              FROM state
        )
        SELECT *, COUNT(*) OVER () AS total FROM judged WHERE latest < %s ORDER BY latest, name LIMIT {STUCK_LIMIT}""",
        (workspace_id, workspace_id, workspace_id, workspace_id, list(WORKING_STAGES),
         today - timedelta(days=STUCK_AFTER_DAYS)),
    )
    rows = [serialize_row(dict(row)) for row in cur.fetchall()]
    total = rows[0]["total"] if rows else 0
    return [{key: value for key, value in row.items() if key != "total"} for row in rows], total


def _open_pipeline(cur, workspace_id: int, offer: str | None) -> dict:
    """Everything still open, all time, by status (expected, booked, contracted)."""
    cur.execute(
        "SELECT status, COALESCE(SUM(amount_eur), 0) AS eur, COUNT(*) AS n FROM sales "
        "WHERE workspace_id = %s AND deleted_at IS NULL AND status = ANY(%s) "
        f"{_sales_offer(workspace_id, offer)} GROUP BY status",
        (workspace_id, list(PIPELINE_SALE_STATUSES)),
    )
    open_sales = {row["status"]: row for row in cur.fetchall()}
    return {status: {"eur": Decimal(open_sales[status]["eur"]) if status in open_sales else Decimal("0"),
                     "count": open_sales[status]["n"] if status in open_sales else 0}
            for status in PIPELINE_SALE_STATUSES}


def _contract_sales(cur, acts_sql: str, base: list, workspace_id: int, start: date, end: date,
                    offer: str | None) -> list[dict]:
    """One row per contract agreed in [start, end] (cancelled ones left out): its total, its payments,
    the weeks from the first contact (or the previous contract's day) and the activities in between."""
    order = ", ".join(f"'{status}'" for status in LIVE_SALE_STATUSES)  # constants, never input
    cur.execute(
        f"""WITH {acts_sql},
        s AS (
            SELECT ct.id AS contract_id, ct.title, x.contact_id, x.person_id,
                   COALESCE(c.name, p.name) AS organization, o.name AS offer,
                   COALESCE(c.created_at, p.created_at)::date AS added_on,
                   (ARRAY[{order}])[MIN(array_position(ARRAY[{order}], s.status))] AS status,
                   SUM(s.amount_eur) AS amount_eur, MIN(s.won_on) AS won_on,
                   MAX(COALESCE(s.series_total, 1)) AS payments
              FROM sales s JOIN contracts ct ON ct.id = s.contract_id AND ct.deleted_at IS NULL
              JOIN deals x ON x.id = s.deal_id
              LEFT JOIN contacts c ON c.id = x.contact_id LEFT JOIN people p ON p.id = x.person_id
              JOIN offers o ON o.id = x.offer_id
             WHERE s.workspace_id = %s AND s.deleted_at IS NULL AND s.status = ANY(%s)
                   {_sales_offer(workspace_id, offer, "s.deal_id")}
             GROUP BY ct.id, ct.title, x.contact_id, x.person_id, c.name, p.name, c.created_at, p.created_at, o.name
        ), timed AS (
            SELECT s.*, LAG(s.won_on) OVER (PARTITION BY COALESCE(s.contact_id, -s.person_id)
                                            ORDER BY s.won_on, s.contract_id) AS previous_won FROM s
        )
        SELECT timed.*,
               LEAST((SELECT MIN(day) FROM acts a WHERE a.contact_id = timed.contact_id), timed.added_on) AS first_contact,
               (SELECT COUNT(*) FROM acts a WHERE a.contact_id = timed.contact_id AND a.kind <> 'note'
                   AND a.day <= timed.won_on AND (timed.previous_won IS NULL OR a.day > timed.previous_won)) AS activities
          FROM timed WHERE timed.won_on BETWEEN %s AND %s ORDER BY timed.won_on DESC, timed.contract_id DESC""",
        base + [workspace_id, list(LIVE_SALE_STATUSES), start, end],
    )
    sales = []
    for row in cur.fetchall():
        sale = dict(row)
        begun = sale["previous_won"] or sale["first_contact"]
        sale["weeks"] = round((sale["won_on"] - begun).days / 7, 1) if begun else None
        sales.append(sale)
    return sales


def _has_subscriptions(cur, workspace_id: int) -> bool:
    cur.execute("SELECT EXISTS (SELECT 1 FROM subscriptions WHERE workspace_id = %s AND deleted_at IS NULL) AS found",
                (workspace_id,))
    return cur.fetchone()["found"]


def get_statistics(workspace_id: int, start: date, end: date, today: date | None = None,
                   offer: str | None = None) -> dict:
    """Everything the Statistics page shows for [start, end] — for one offer, or
    for every offer when `offer` is None. New contacts are counted either way:
    a contact is not created for an offer."""
    today = today or date.today()
    defaults = get_minute_defaults(workspace_id)
    acts_sql, acts_params = activities_sql(defaults, offer, workspace_id)
    base = acts_params + [workspace_id, workspace_id, *NOT_ACTIVITIES]
    prev_start, prev_end = previous_period(start, end)
    with db() as conn:
        cur = conn.cursor()
        current = _summary(cur, acts_sql, acts_params, workspace_id, start, end, offer, today)
        previous = _summary(cur, acts_sql, acts_params, workspace_id, prev_start, prev_end, offer, today)
        recurring = mrr_now(cur, workspace_id, offer, today)
        stuck, stuck_total = stuck_deals(cur, workspace_id, offer, today)
        return {
            "start": start, "end": end, "previous_start": prev_start, "previous_end": prev_end,
            "current": current, "previous": previous,
            "new_by_source": _new_by_source(cur, workspace_id, start, end),
            "stages_now": _stages_now(cur, workspace_id, offer),
            "stuck": stuck, "stuck_total": stuck_total, "stuck_after_days": STUCK_AFTER_DAYS,
            "sales": _contract_sales(cur, acts_sql, base, workspace_id, start, end, offer),
            "pipeline": _open_pipeline(cur, workspace_id, offer), "defaults": defaults, "offer": offer,
            "mrr_now": recurring["mrr"], "subscribers_now": recurring["subscribers"],
            "has_subscriptions": _has_subscriptions(cur, workspace_id),
        }
