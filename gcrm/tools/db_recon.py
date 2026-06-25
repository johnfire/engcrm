"""Proximity query for the mobile recon view — contacts nearest a GPS point."""
from gcrm.db.connection import db, serialize_row

# Statuses that mean "already worked" — excluded when not_contacted=True.
_CONTACTED = ("contacted", "meeting", "proposal", "accepted", "rejected", "opt_out", "do_not_contact")


def get_contacts_near(lat: float, lng: float, not_contacted: bool = False, limit: int = 50) -> list[dict]:
    """Contacts that have coordinates, nearest the given point first, each with a
    distance_m. Skips soft-deleted and permanently/temporarily closed businesses."""
    clauses = [
        "latitude IS NOT NULL",
        "deleted_at IS NULL",
        "(business_status IS NULL OR business_status = 'OPERATIONAL')",
    ]
    params = {"lat": lat, "lng": lng, "limit": limit}
    if not_contacted:
        clauses.append("(status IS NULL OR status NOT IN %(contacted)s)")
        params["contacted"] = _CONTACTED
    where = " AND ".join(clauses)
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT id, name, type, city, latitude, longitude, rating, user_ratings,
                   business_status, status, fit_score, phone, website,
                   google_data->>'googleMapsUri' AS maps_uri,
                   (6371000 * acos(least(1, greatest(-1,
                       cos(radians(%(lat)s)) * cos(radians(latitude)) *
                       cos(radians(longitude) - radians(%(lng)s)) +
                       sin(radians(%(lat)s)) * sin(radians(latitude))
                   )))) AS distance_m
            FROM contacts
            WHERE {where}
            ORDER BY distance_m
            LIMIT %(limit)s
            """,
            params,
        )
        return [serialize_row(dict(row)) for row in cur.fetchall()]
