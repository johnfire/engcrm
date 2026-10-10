"""How many people and organizations were actually contacted, this month and since the business began."""
from datetime import date, datetime
from zoneinfo import ZoneInfo

from gcrm.db.connection import db
from gcrm.tools.db_contact_dates import CONTACT_HISTORY_FILTER, CONTACT_TIMEZONE, contact_day_sql
from gcrm.tools.db_deals import offer_id_sql

# The day the business officially began; "all time" counts nothing earlier.
BUSINESS_START = date(2026, 10, 1)


def today() -> date:
    return datetime.now(ZoneInfo(CONTACT_TIMEZONE)).date()


def count_contacted(first_day: date, last_day: date, workspace_id: int | None, offer: str | None = None) -> dict:
    """Distinct people, and distinct organizations reached directly or through one of
    their people, with a real contact (not a planned next step) on a day in the range.
    With an `offer`, only contacts logged as being about that offer count."""
    scope = " AND workspace_id=%s" if workspace_id is not None else ""
    scope_args = [workspace_id] if workspace_id is not None else []
    person_day = contact_day_sql("person", "occurred_at")
    person_offer = f" AND offer_id = {offer_id_sql('person.workspace_id', offer)}" if offer else ""
    organization_offer = f" AND offer_id = {offer_id_sql('organization.workspace_id', offer)}" if offer else ""
    person_contacted = (f"EXISTS (SELECT 1 FROM people_interactions WHERE person_id=person.id "
                        f"AND {CONTACT_HISTORY_FILTER} AND {person_day} BETWEEN %s AND %s{person_offer})")
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute(f"SELECT COUNT(*) AS n FROM people person WHERE deleted_at IS NULL{scope} AND {person_contacted}",
                       scope_args + [first_day, last_day])
        people = cursor.fetchone()["n"]
        cursor.execute(
            f"SELECT COUNT(*) AS n FROM contacts organization WHERE deleted_at IS NULL{scope} AND ("
            f"EXISTS (SELECT 1 FROM interactions WHERE contact_id=organization.id AND {CONTACT_HISTORY_FILTER} "
            f"AND interaction_date BETWEEN %s AND %s{organization_offer}) OR EXISTS (SELECT 1 FROM people person "
            f"WHERE person.contact_id=organization.id AND person.deleted_at IS NULL AND {person_contacted}))",
            scope_args + [first_day, last_day, first_day, last_day])
        organizations = cursor.fetchone()["n"]
    return {"people": people, "organizations": organizations}


def get_contact_counts(workspace_id: int | None, on: date | None = None, offer: str | None = None) -> dict:
    day = on or today()
    return {
        "month": count_contacted(day.replace(day=1), day, workspace_id, offer),
        "since_start": count_contacted(BUSINESS_START, day, workspace_id, offer),
        "month_start": day.replace(day=1).isoformat(),
        "business_start": BUSINESS_START.isoformat(),
    }
