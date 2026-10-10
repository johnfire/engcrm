"""Proximity query for the mobile recon view — contacts nearest a GPS point."""
from gcrm.db.connection import db, serialize_row
from gcrm.tools.db_deals import organization_deal_join

# Anything past first contact counts as "already worked" and is excluded when
# not_contacted=True. Stage carries that now: a candidate or suspect that is
# only 'ready' has never been written to, everything beyond has.
_WORKED_STAGES = ("prospect", "opportunity", "customer", "not_in_pipeline")
_WORKED_STATUSES = ("contacted", "meeting", "proposal", "dropped")


def get_organizations_near(lat: float, lng: float, not_contacted: bool = False, limit: int = 50) -> list[dict]:
    """Contacts that have coordinates, nearest the given point first, each with a
    distance_m. Skips soft-deleted and permanently/temporarily closed businesses."""
    clauses = [
        "c.latitude IS NOT NULL",
        "c.deleted_at IS NULL",
        "(c.business_status IS NULL OR c.business_status = 'OPERATIONAL')",
    ]
    params = {"lat": lat, "lng": lng, "limit": limit}
    if not_contacted:
        clauses.append("(d.pipeline_stage IS NULL OR d.pipeline_stage NOT IN %(worked_stages)s)")
        clauses.append("(d.status IS NULL OR d.status NOT IN %(worked_statuses)s)")
        clauses.append("c.do_not_contact = FALSE")
        params["worked_stages"] = _WORKED_STAGES
        params["worked_statuses"] = _WORKED_STATUSES
    where = " AND ".join(clauses)
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT c.id, c.name, c.type, c.city, c.latitude, c.longitude, c.rating, c.user_ratings,
                   c.business_status, d.pipeline_stage, d.status, c.do_not_contact,
                   c.fit_score, c.phone, c.website,
                   c.google_data->>'googleMapsUri' AS maps_uri,
                   (6371000 * acos(least(1, greatest(-1,
                       cos(radians(%(lat)s)) * cos(radians(c.latitude)) *
                       cos(radians(c.longitude) - radians(%(lng)s)) +
                       sin(radians(%(lat)s)) * sin(radians(c.latitude))
                   )))) AS distance_m
            FROM contacts c {organization_deal_join("c", "d")}
            WHERE {where}
            ORDER BY distance_m
            LIMIT %(limit)s
            """,
            params,
        )
        return [serialize_row(dict(row)) for row in cur.fetchall()]
