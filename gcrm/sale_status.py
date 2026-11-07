"""The life of a sale. Only a collected sale is money won; booked and contracted
ones are the pipeline, and a cancelled one is kept so you can see what fell through.

booked      agreed, nothing in writing yet
contracted  a written contract exists
collected   the money is in
cancelled   it fell through
"""
from datetime import date

SALE_STATUSES = ("booked", "contracted", "collected", "cancelled")
PIPELINE_SALE_STATUSES = ("booked", "contracted")
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
