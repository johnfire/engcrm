"""What a contract is worth, when it runs, and which section of the Contracts list it belongs in.

A contract holds no money of its own: everything here is worked out from its payments (its live sales), so
the Contracts page and the Forecast read the same rows and cannot disagree. Pure functions, no database.

A payment is a dict with `amount_eur`, `status`, `hours`, `won_on`, `expected_on`, `work_from` and `work_to`
(only the first three matter for the money; the rest for the dates)."""
from datetime import date
from decimal import Decimal

from gcrm.contract_kinds import CONTRACT_KINDS
from gcrm.sale_series import rate_of

SECTIONS = ("running", "upcoming", "finished")
# The ways the list can be sorted inside each section. None (no choice) keeps the timing order.
SORT_KEYS = ("customer", "kind", "dates", "value")
_ZERO = Decimal("0")

# Where a contract's dates come from, best source first: the days the work is done, else the days the
# payments are due, else the days it was won. The first source that has dates decides, for the whole contract.
_DATE_SOURCES = (("work_from", "work_to"), ("expected_on", "expected_on"), ("won_on", "won_on"))


def _span(payments: list[dict]) -> tuple[date | None, date | None]:
    """(start, end) of the contract. Payments without a date at the chosen level are skipped, so a mix of
    dated and undated ones is no gap. Cancelled payments are left out, unless every payment is cancelled
    (then they are all there is, and the contract still needs a place to sort)."""
    counted = [p for p in payments if p["status"] != "cancelled"] or payments
    for first, last in _DATE_SOURCES:
        starts = [p[first] for p in counted if p.get(first)]
        ends = [p[last] for p in counted if p.get(last)]
        if starts and ends:
            return min(starts), max(ends)
    return None, None


def contract_summary(payments: list[dict]) -> dict:
    """{value, hours, rate, collected, open, start, end, cancelled, payments} of a contract's payments.
    Cancelled payments count for nothing; `hours` is None when none is recorded; `rate` is value over hours,
    only with hours; collected + open = value; `cancelled` is True when every payment is (a contract with no
    payment at all is not cancelled, only empty: 0 euros, no dates)."""
    counted = [p for p in payments if p["status"] != "cancelled"]
    value = sum((Decimal(str(p["amount_eur"])) for p in counted), _ZERO)
    collected = sum((Decimal(str(p["amount_eur"])) for p in counted if p["status"] == "collected"), _ZERO)
    hours = sum((Decimal(str(p["hours"])) for p in counted if p.get("hours")), _ZERO) or None
    start, end = _span(payments)
    return {"value": value, "hours": hours, "rate": rate_of(value, hours), "collected": collected,
            "open": value - collected, "start": start, "end": end,
            "cancelled": bool(payments) and not counted, "payments": len(payments)}


def timing(summary: dict, today: date) -> str:
    """"running" (start <= today <= end), "upcoming" (start after today) or "finished" (ended before today,
    cancelled, or with no dates to say otherwise)."""
    if summary["cancelled"] or summary["start"] is None or summary["end"] < today:
        return "finished"
    return "upcoming" if summary["start"] > today else "running"


def _sort_value(contract: dict, key: str):
    """What `key` sorts a contract on, or None when it has nothing to sort by (then it goes last)."""
    if key == "customer":
        return (contract.get("owner_name") or "").casefold() or None
    if key == "kind":
        kind = contract.get("kind")
        return CONTRACT_KINDS.index(kind) if kind in CONTRACT_KINDS else None
    if key == "dates":
        return contract["summary"]["start"]
    return contract["summary"]["value"]


def sort_contracts(contracts: list[dict], key: str, descending: bool = False) -> list[dict]:
    """The contracts sorted by `key` (one of SORT_KEYS): customer name ignoring case, kind in the order of
    CONTRACT_KINDS, start date, or value. `descending` turns only that order round; equal ones always follow
    by customer, then title, and a contract with nothing to sort by (no dates, an unknown kind) is last either
    way. ValueError for another key."""
    if key not in SORT_KEYS:
        raise ValueError(f"unknown contract sort {key!r}; one of {', '.join(SORT_KEYS)}")
    tie_order = sorted(contracts, key=lambda c: ((c.get("owner_name") or "").casefold(), c["title"].casefold(), c.get("id", 0)))
    known = [c for c in tie_order if _sort_value(c, key) is not None]
    blank = [c for c in tie_order if _sort_value(c, key) is None]
    known.sort(key=lambda c: _sort_value(c, key), reverse=descending)       # stable: ties keep the tie order
    return known + blank


def group_by_timing(contracts: list[dict], today: date, sort: str | None = None,
                    descending: bool = False) -> dict[str, list[dict]]:
    """The contracts (each with a `summary`) in their three sections, every section present. With a `sort`
    (one of SORT_KEYS) each section is in that order (see sort_contracts); without, as the list shows them by
    default: running by soonest end, upcoming by soonest start, finished by latest end (a contract without
    dates last), ties by title."""
    groups: dict[str, list[dict]] = {name: [] for name in SECTIONS}
    for contract in sorted(contracts, key=lambda c: (c["title"].lower(), c.get("id", 0))):
        groups[timing(contract["summary"], today)].append(contract)
    if sort is not None:
        return {name: sort_contracts(found, sort, descending) for name, found in groups.items()}
    groups["running"].sort(key=lambda c: c["summary"]["end"])
    groups["upcoming"].sort(key=lambda c: c["summary"]["start"])
    groups["finished"].sort(key=lambda c: c["summary"]["end"] or date.min, reverse=True)
    return groups


def totals(contracts: list[dict]) -> dict:
    """{count, cancelled, value, hours, rate, collected, open} over these contracts. Cancelled contracts are
    counted apart and add nothing. The average rate is taken only over contracts that recorded hours:
    money from contracts with no hours says nothing about what an hour earns."""
    live = [c["summary"] for c in contracts if not c["summary"]["cancelled"]]
    value = sum((s["value"] for s in live), _ZERO)
    collected = sum((s["collected"] for s in live), _ZERO)
    hours = sum((s["hours"] for s in live if s["hours"]), _ZERO) or None
    timed_value = sum((s["value"] for s in live if s["hours"]), _ZERO)
    return {"count": len(live), "cancelled": len(contracts) - len(live), "value": value, "hours": hours,
            "rate": rate_of(timed_value, hours), "collected": collected, "open": value - collected}
