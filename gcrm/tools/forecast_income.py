"""The Forecast's money for one calendar year, split the way the income calculator needs it.

A sale counts in the year it was received (collected) or is due; cancelled money is left
out, and money with no due day cannot be placed in a year, so it is reported apart. The
contract's kind decides the tax treatment: a teaching course is VAT-exempt teaching,
consulting and workshops are taxable, and "other" is listed but not counted until someone
gives it a kind. Read-only; run inside the workspace's scope.
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from gcrm.db.connection import db
from gcrm.forecast_math import first_booking_month, new_sales_cash
from gcrm.tools.income_plan import get_plan
from gcrm.tools.revenue import live_sales_sql

TEACHING_KINDS = ("teaching_course",)
TAXABLE_KINDS = ("consulting", "workshop")
ALWAYS_COUNTED = ("collected", "contracted", "booked")
_ZERO = Decimal("0")


@dataclass(frozen=True)
class IncomeLine:
    contract_id: int
    title: str
    customer: str
    kind: str
    eur: Decimal
    count: int


@dataclass(frozen=True)
class ForecastIncome:
    consulting: Decimal                 # taxable, including possible new sales counted as such
    teaching: Decimal                   # VAT-exempt, including possible new sales counted as such
    possible: Decimal                   # the assumed new sales included in one of the two above
    possible_as: str                    # "consulting" or "teaching"
    lines: tuple[IncomeLine, ...]       # what was counted, one per contract
    unclassified: tuple[IncomeLine, ...]
    undated_total: Decimal
    undated_count: int


def _lines(rows: list[dict]) -> tuple[IncomeLine, ...]:
    by_contract: dict[int, IncomeLine] = {}
    for row in rows:
        seen = by_contract.get(row["contract_id"])
        by_contract[row["contract_id"]] = IncomeLine(
            row["contract_id"], row["title"], row["customer"], row["kind"],
            (seen.eur if seen else _ZERO) + Decimal(row["eur"]), (seen.count if seen else 0) + row["n"])
    return tuple(by_contract.values())


def summarise(rows: list[dict], possible: Decimal, possible_as: str) -> ForecastIncome:
    dated = [row for row in rows if not row["undated"]]
    undated = [row for row in rows if row["undated"]]
    counted = [row for row in dated if row["kind"] in TEACHING_KINDS + TAXABLE_KINDS]

    def total(kinds: tuple[str, ...]) -> Decimal:
        return sum((Decimal(row["eur"]) for row in counted if row["kind"] in kinds), _ZERO)

    return ForecastIncome(
        consulting=total(TAXABLE_KINDS) + (possible if possible_as == "consulting" else _ZERO),
        teaching=total(TEACHING_KINDS) + (possible if possible_as == "teaching" else _ZERO),
        possible=possible, possible_as=possible_as,
        lines=_lines(counted),
        unclassified=_lines([row for row in dated if row not in counted]),
        undated_total=sum((Decimal(row["eur"]) for row in undated), _ZERO),
        undated_count=sum(row["n"] for row in undated),
    )


def _sale_rows(workspace_id: int, statuses: list[str], first: date, last: date) -> list[dict]:
    scope, params = live_sales_sql(workspace_id, None)
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT x.contract_id, k.title, k.kind, x.customer, x.due IS NULL AS undated, "
            "       SUM(x.amount_eur) AS eur, COUNT(*) AS n FROM ("
            "  SELECT s.contract_id, s.amount_eur, COALESCE(c.name, p.name) AS customer, "
            "         CASE WHEN s.status = 'collected' THEN s.collected_on ELSE s.expected_on END AS due "
            f"  {scope} AND s.status = ANY(%s)"
            ") x JOIN contracts k ON k.id = x.contract_id "
            "WHERE x.due IS NULL OR x.due BETWEEN %s AND %s "
            "GROUP BY x.contract_id, k.title, k.kind, x.customer, x.due IS NULL "
            "ORDER BY x.customer, k.title, x.contract_id",
            [*params, statuses, first, last],
        )
        return [dict(row) for row in cur.fetchall()]


def _possible_new_sales(year: int, today: date) -> Decimal:
    plan = get_plan()
    months = [date(year, month, 1) for month in range(1, 13)]
    cash = new_sales_cash(plan["expected_new_monthly"], plan["expected_new_months"], plan["expected_new_delay"],
                          first_booking_month(today), months, plan["expected_new_campaign"])
    return sum(cash.values(), _ZERO)


def get_forecast_income(workspace_id: int, year: int, *, include_expected: bool, include_possible: bool,
                        possible_as: str, today: date | None = None) -> ForecastIncome:
    statuses = list(ALWAYS_COUNTED) + (["expected"] if include_expected else [])
    rows = _sale_rows(workspace_id, statuses, date(year, 1, 1), date(year, 12, 31))
    possible = _possible_new_sales(year, today or date.today()) if include_possible else _ZERO
    return summarise(rows, possible, possible_as)
