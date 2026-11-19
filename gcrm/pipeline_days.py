"""Days an organization has taken to go from first contact to customer.

Only relationships that have actually started are measured: nibble, prospect,
opportunity and customer. Candidates and suspects have no figure — nobody has
answered yet, so a clock on them would only count our own silence.
"""
from datetime import date, datetime

MEASURED_STAGES = ("nibble", "prospect", "opportunity", "customer")


def _as_date(value) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    return value


def days_to_customer(deals, first_contact, customer_since, today: date | None = None) -> int | None:
    """Days from `first_contact` until the organization became a customer, or
    until `today` while it is not one yet. None when no deal is at a measured
    stage, there was no contact yet, or a customer's date was never recorded
    (a guess would be worse than a blank)."""
    first = _as_date(first_contact)
    stages = {d["stage"] for d in deals or []}
    if first is None or not stages & set(MEASURED_STAGES):
        return None
    if "customer" in stages:
        end = _as_date(customer_since)
        if end is None:
            return None
    else:
        end = today or date.today()
    return max((end - first).days, 0)
