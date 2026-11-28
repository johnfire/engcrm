"""The life of a sale. Booked, contracted and collected sales are sold; only a collected
one is money in. Expected sales are an estimate, and a cancelled one is kept so you can
see what fell through.

expected    estimated: a conservative forecast built on solid facts (a verbal agreement,
            the going market rate), not yet in writing
booked      agreed, nothing in writing yet
contracted  a written contract exists
collected   the money is in
cancelled   it fell through
"""
from datetime import date

SALE_STATUSES = ("expected", "booked", "contracted", "collected", "cancelled")
FIRM_PIPELINE_STATUSES = ("booked", "contracted")  # agreed, not yet paid
PIPELINE_SALE_STATUSES = ("expected",) + FIRM_PIPELINE_STATUSES  # everything still open
SOLD_STATUSES = FIRM_PIPELINE_STATUSES + ("collected",)  # agreed for sure, paid or not
LIVE_SALE_STATUSES = ("expected",) + SOLD_STATUSES  # everything but cancelled
DEFAULT_SALE_STATUS = "collected"  # what a sale was before statuses existed


def checked_sale_status(status: str | None) -> str:
    """The status, or ValueError. Blank is the default (collected)."""
    value = (status or DEFAULT_SALE_STATUS).strip()
    if value not in SALE_STATUSES:
        raise ValueError(f"unknown sale status {status!r}")
    return value


def collected_day(status: str, collected_on: date | None, fallback: date) -> date | None:
    """The day the money came in: only a collected sale has one. A collected sale
    with no day given is collected on `fallback`."""
    if status != "collected":
        return None
    return collected_on or fallback
