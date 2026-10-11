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
from gcrm.tools.db_audit import log_audit
from gcrm.tools.db_deals import CONSULTING, offer_id_sql

PERIODS = ("week", "month", "quarter", "year")
WORKING_STAGES = ("suspect", "prospect", "opportunity")
STUCK_AFTER_DAYS = 28
_FORWARD_ORDER = [s for s in PIPELINE_STAGES if s != "not_in_pipeline"]


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
             deal_id: int | None = None) -> int | None:
    """Record a sale on an organization of this workspace, for one of its deals
    (`deal_id`; its Consulting deal when not given). None if there is no such
    organization, or no such live deal of it."""
    if amount_eur <= 0:
        raise ValueError("amount must be more than 0")
    which = "x.id = %s" if deal_id is not None else f"x.offer_id = {offer_id_sql('c.workspace_id', CONSULTING)}"
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO sales (workspace_id, deal_id, amount_eur, won_on, description) "
            "SELECT %s, x.id, %s, %s, %s FROM contacts c JOIN deals x ON x.contact_id = c.id "
            f"WHERE c.id = %s AND c.workspace_id = %s AND c.deleted_at IS NULL AND x.deleted_at IS NULL "
            f"AND {which} RETURNING id",
            [workspace_id, amount_eur, won_on, description.strip() or None, contact_id, workspace_id,
             *([deal_id] if deal_id is not None else [])],
        )
        row = cur.fetchone()
    if row:
        log_audit(None, None, "sale.added", f"contact:{contact_id}", f"{amount_eur} EUR on {won_on}")
    return row["id"] if row else None


def get_sales(contact_id: int) -> list[dict]:
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT s.id, s.amount_eur, s.won_on, s.description, o.name AS offer FROM sales s "
            "JOIN deals d ON d.id = s.deal_id JOIN offers o ON o.id = d.offer_id "
            "WHERE d.contact_id = %s AND s.deleted_at IS NULL ORDER BY s.won_on DESC, s.id DESC",
            (contact_id,),
        )
        return [serialize_row(dict(row)) for row in cur.fetchall()]


def delete_sale(contact_id: int, sale_id: int) -> bool:
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE sales SET deleted_at = NOW() WHERE id = %s AND deleted_at IS NULL "
            "AND deal_id IN (SELECT id FROM deals WHERE contact_id = %s)",
            (sale_id, contact_id),
        )
        deleted = cur.rowcount > 0
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
    cur.execute(
        "SELECT COALESCE(SUM(amount_eur), 0) AS won, COUNT(*) AS sales FROM sales "
        f"WHERE workspace_id = %s AND deleted_at IS NULL AND won_on BETWEEN %s AND %s{_sales_offer(workspace_id, offer)}",
        (workspace_id, start, end),
    )
    money = cur.fetchone()
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
    minutes = sum(e["minutes"] for e in effort.values())
    activities = sum(e["count"] for kind, e in effort.items() if kind != "note")
    one_off = Decimal(money["won"])
    won = one_off + subscriptions
    return {
        "effort": effort,
        "activities": activities,
        "minutes": minutes,
        "hours": round(minutes / 60, 1),
        "estimated": sum(e["estimated"] for e in effort.values()),
        "won_eur": won,
        "one_off_eur": one_off,
        "subscription_eur": subscriptions,
        "new_mrr": moves["new_mrr"],
        "lost_mrr": moves["lost_mrr"],
        "sales": money["sales"],
        "eur_per_hour": round(won / Decimal(minutes) * 60, 2) if minutes else None,
        "stage_changes": changes,
        "promotions": sum(c["n"] for c in changes if c["direction"] == "forward"),
        "new_organizations": new["organizations"],
        "new_people": new["people"],
    }


def stage_direction(from_stage: str | None, to_stage: str | None) -> str:
    """forward / back / dropped / other, along candidate → … → customer."""
    if to_stage == "not_in_pipeline":
        return "dropped"
    if from_stage in _FORWARD_ORDER and to_stage in _FORWARD_ORDER:
        return "forward" if _FORWARD_ORDER.index(to_stage) > _FORWARD_ORDER.index(from_stage) else "back"
    return "other"


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
    only = f"AND d.offer_id = {_offer_sql(workspace_id, offer)} " if offer else ""
    with db() as conn:
        cur = conn.cursor()
        current = _summary(cur, acts_sql, acts_params, workspace_id, start, end, offer, today)
        previous = _summary(cur, acts_sql, acts_params, workspace_id, prev_start, prev_end, offer, today)
        recurring = mrr_now(cur, workspace_id, offer, today)

        cur.execute(
            f"WITH {acts_sql} SELECT date_trunc('week', day)::date AS week, COUNT(*) FILTER "
            "(WHERE kind <> 'note') AS n, SUM(minutes) AS minutes FROM acts "
            "WHERE day BETWEEN %s AND %s GROUP BY 1 ORDER BY 1",
            base + [start, end],
        )
        weeks = [{"week": row["week"], "count": row["n"], "minutes": int(row["minutes"] or 0)}
                 for row in cur.fetchall()]

        cur.execute(
            "SELECT 'organization' AS kind, COALESCE(NULLIF(source, ''), 'unknown') AS source, COUNT(*) AS n "
            "FROM contacts WHERE workspace_id = %s AND deleted_at IS NULL AND created_at::date BETWEEN %s AND %s "
            "GROUP BY 2 UNION ALL "
            "SELECT 'person', COALESCE(NULLIF(source, ''), 'unknown'), COUNT(*) FROM people "
            "WHERE workspace_id = %s AND deleted_at IS NULL AND created_at::date BETWEEN %s AND %s "
            "GROUP BY 2 ORDER BY 1, 3 DESC",
            (workspace_id, start, end, workspace_id, start, end),
        )
        new_by_source = [dict(row) for row in cur.fetchall()]

        cur.execute(
            "SELECT CASE WHEN d.contact_id IS NOT NULL THEN 'organization' ELSE 'person' END AS kind, "
            "d.pipeline_stage AS stage, COUNT(*) AS n FROM deals d "
            "LEFT JOIN contacts c ON c.id = d.contact_id LEFT JOIN people p ON p.id = d.person_id "
            "WHERE d.workspace_id = %s AND d.deleted_at IS NULL AND c.deleted_at IS NULL AND p.deleted_at IS NULL "
            f"{only}GROUP BY 1, 2",
            (workspace_id,),
        )
        stages_now = {"organization": {}, "person": {}}
        for row in cur.fetchall():
            stages_now[row["kind"]][row["stage"]] = row["n"]

        cur.execute(
            f"WITH {acts_sql}, last AS (SELECT contact_id, MAX(day) AS last_day FROM acts GROUP BY contact_id) "
            "SELECT c.id, c.name, d.pipeline_stage, o.name AS offer, last.last_day FROM deals d "
            "JOIN contacts c ON c.id = d.contact_id JOIN offers o ON o.id = d.offer_id "
            "LEFT JOIN last ON last.contact_id = c.id "
            f"WHERE c.workspace_id = %s AND c.deleted_at IS NULL AND d.deleted_at IS NULL {only}"
            "AND d.pipeline_stage = ANY(%s) "
            "AND (last.last_day IS NULL OR last.last_day < %s) "
            "ORDER BY last.last_day ASC NULLS FIRST, c.name LIMIT 25",
            base + [workspace_id, list(WORKING_STAGES), today - timedelta(days=STUCK_AFTER_DAYS)],
        )
        stuck = [serialize_row(dict(row)) for row in cur.fetchall()]

        cur.execute(
            f"""WITH {acts_sql},
            s AS (
                SELECT s.id, x.contact_id, s.amount_eur, s.won_on, s.description, c.name AS organization,
                       c.created_at::date AS added_on, o.name AS offer,
                       LAG(s.won_on) OVER (PARTITION BY x.contact_id ORDER BY s.won_on, s.id) AS previous_won
                  FROM sales s JOIN deals x ON x.id = s.deal_id JOIN contacts c ON c.id = x.contact_id
                  JOIN offers o ON o.id = x.offer_id
                 WHERE s.workspace_id = %s AND s.deleted_at IS NULL{_sales_offer(workspace_id, offer, "s.deal_id")}
            )
            SELECT s.*,
                   LEAST((SELECT MIN(day) FROM acts a WHERE a.contact_id = s.contact_id), s.added_on) AS first_contact,
                   (SELECT COUNT(*) FROM acts a WHERE a.contact_id = s.contact_id AND a.kind <> 'note'
                       AND a.day <= s.won_on AND (s.previous_won IS NULL OR a.day > s.previous_won)) AS activities,
                   (SELECT COALESCE(SUM(minutes), 0) FROM acts a WHERE a.contact_id = s.contact_id
                       AND a.day <= s.won_on AND (s.previous_won IS NULL OR a.day > s.previous_won)) AS minutes
              FROM s WHERE s.won_on BETWEEN %s AND %s ORDER BY s.won_on DESC, s.id DESC""",
            base + [workspace_id, start, end],
        )
        sales = []
        for row in cur.fetchall():
            sale = dict(row)
            begun = sale["previous_won"] or sale["first_contact"]
            sale["weeks"] = round((sale["won_on"] - begun).days / 7, 1) if begun else None
            sale["hours"] = round(int(sale["minutes"]) / 60, 1)
            sale["eur_per_hour"] = (round(Decimal(sale["amount_eur"]) / Decimal(sale["minutes"]) * 60, 2)
                                    if sale["minutes"] else None)
            sales.append(sale)

    return {
        "start": start, "end": end, "previous_start": prev_start, "previous_end": prev_end,
        "current": current, "previous": previous, "weeks": weeks, "new_by_source": new_by_source,
        "stages_now": stages_now, "stuck": stuck, "stuck_after_days": STUCK_AFTER_DAYS,
        "sales": sales, "defaults": defaults, "offer": offer,
        "mrr_now": recurring["mrr"], "subscribers_now": recurring["subscribers"],
    }
