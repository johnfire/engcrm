"""Map pins: which organizations are on one of the user's Google Maps lists.

Maps' private saved list "Cold call candidates" is what the phone shows while walking
around looking for businesses to visit. This module records, in the CRM, what has been
pinned there, so the two stay in step: an organization can be asked "are you on the
map?", a candidate that was never pinned can be found, and nothing is pinned twice.
Saving a pin in Maps itself is done in the browser (the marketing-leads-to-google-maps
skill); this only keeps the record. A pin is identified by Google's id of the place.
"""
import re

from gcrm.db.connection import db
from gcrm.tools.db_audit import log_audit

COLD_CALL_CANDIDATES = "Cold call candidates"

# The place's own id is the first !1s in its link; !5s is a search id and must not be taken.
_PLACE_KEY = re.compile(r"!1s(0x[0-9a-f]+:0x[0-9a-f]+)")


def place_key_from_url(url: str | None) -> str | None:
    """Google's id of the place a Maps link points at, or None for a link that is not a place."""
    match = _PLACE_KEY.search(url or "")
    return match.group(1) if match else None


def record_pin(contact_id: int, place_key: str, maps_name: str, *, list_name: str = COLD_CALL_CANDIDATES,
               maps_address: str = "", maps_url: str = "", latitude: float | None = None,
               longitude: float | None = None, note: str = "") -> dict | None:
    """Record that `contact_id` is pinned on `list_name` as the place `place_key`. Recording
    the same pin again updates what Maps shows (name, address, note) and keeps the first
    saved_at, so it is safe to repeat. A pin that was removed and is pinned again comes
    back as a new row. Returns the pin, or None when there is no such organization."""
    if not place_key or not maps_name:
        raise ValueError("a pin needs the place's Google id and the name Maps shows")
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO map_pins (workspace_id, contact_id, list_name, place_key, maps_name, maps_address,
                                  maps_url, latitude, longitude, note)
            SELECT c.workspace_id, c.id, %s, %s, %s, %s, %s, %s, %s, %s
              FROM contacts c WHERE c.id = %s AND c.deleted_at IS NULL
            ON CONFLICT (contact_id, list_name, place_key) WHERE removed_at IS NULL
            DO UPDATE SET maps_name = EXCLUDED.maps_name, maps_address = EXCLUDED.maps_address,
                          maps_url = EXCLUDED.maps_url, latitude = EXCLUDED.latitude,
                          longitude = EXCLUDED.longitude, note = EXCLUDED.note
            RETURNING *
            """,
            (list_name, place_key, maps_name.strip(), maps_address.strip(), maps_url.strip(), latitude, longitude,
             note.strip(), contact_id),
        )
        row = cur.fetchone()
    if row is None:
        return None
    log_audit(None, None, "map_pin.recorded", f"contact:{contact_id}", f"{list_name}: {maps_name.strip()}"[:200])
    return dict(row)


def remove_pin(pin_id: int) -> bool:
    """Mark a pin as no longer on the map (it was taken off the list). It stays on record."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE map_pins SET removed_at = NOW() WHERE id = %s AND removed_at IS NULL "
                    "RETURNING contact_id, list_name, maps_name", (pin_id,))
        row = cur.fetchone()
    if row is None:
        return False
    log_audit(None, None, "map_pin.removed", f"contact:{row['contact_id']}", f"{row['list_name']}: {row['maps_name']}"[:200])
    return True


def pins_for_contact(contact_id: int) -> list[dict]:
    """The live pins of one organization, oldest first."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM map_pins WHERE contact_id = %s AND removed_at IS NULL ORDER BY saved_at, id",
                    (contact_id,))
        return [dict(row) for row in cur.fetchall()]


def candidates_not_on_map(workspace_id: int, list_name: str = COLD_CALL_CANDIDATES, limit: int = 100) -> list[dict]:
    """Organizations at the candidate stage (consulting) with a location but no live pin on `list_name`,
    in id order so a batch resumes where the last one stopped. Not contacted yet and not
    do-not-contact: the same rule as the list itself."""
    return pin_queue(workspace_id, list_name=list_name, limit=limit)


def pin_queue(workspace_id: int, ids: list[int] | None = None, list_name: str = COLD_CALL_CANDIDATES,
              limit: int = 200) -> list[dict]:
    """Companies waiting to be pinned on `list_name`: with a location (coordinates or an
    address), not pinned yet, not do-not-contact, no logged activity. With `ids` (a Gather
    run's companies) any stage counts; without, only candidates, as the list has always held."""
    scope, params = ("c.id = ANY(%s)", [list(ids)]) if ids is not None else ("d.pipeline_stage = 'candidate'", [])
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT c.id, c.name, c.city, c.type, c.address, c.latitude, c.longitude, c.website
              FROM contacts c
              JOIN deals d ON d.contact_id = c.id AND d.deleted_at IS NULL
                          AND d.offer_id = offer_id_for(c.workspace_id, 'consulting')
             WHERE c.workspace_id = %s AND c.deleted_at IS NULL AND {scope}
               AND NOT c.do_not_contact
               AND (c.latitude IS NOT NULL OR COALESCE(c.address, '') <> '')
               AND NOT EXISTS (SELECT 1 FROM interactions i WHERE i.contact_id = c.id)
               AND NOT EXISTS (SELECT 1 FROM map_pins p WHERE p.contact_id = c.id AND p.list_name = %s
                                AND p.removed_at IS NULL)
             ORDER BY c.id LIMIT %s
            """,
            (workspace_id, *params, list_name, limit),
        )
        return [dict(row) for row in cur.fetchall()]


def latest_gather_ids() -> list[int]:
    """The companies the most recent finished Gather run found (empty if none)."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT output_json FROM agent_runs WHERE agent_name = 'gather' AND status = 'completed' "
                    "ORDER BY started_at DESC, id DESC LIMIT 1")
        row = cur.fetchone()
    output = (row or {}).get("output_json") or {}
    return [int(contact_id) for contact_id in output.get("saved_ids", [])]


PINNED_STATUSES = ("saved", "already")
PLACE_KEY_SHAPE = re.compile(r"0x[0-9a-f]+:0x[0-9a-f]+")


def apply_pin_result(result: dict, list_name: str = COLD_CALL_CANDIDATES) -> str:
    """Record one result of the browser pin loop. Only a place the loop saw saved on the
    list is recorded; the organization's blank address, phone, website and coordinates are
    filled from Maps, and nothing already there is replaced. Returns what happened."""
    status = result.get("status")
    if status not in PINNED_STATUSES:
        return f"skipped: {status}"
    if not PLACE_KEY_SHAPE.fullmatch(result.get("key") or ""):
        return "bad key"
    distance = f"{result['dist']} m from the CRM location" if result.get("dist") is not None else "found by address"
    pin = record_pin(result["id"], result["key"], result.get("title") or "", list_name=list_name,
                     maps_address=result.get("address") or "", latitude=result.get("lat"),
                     longitude=result.get("lon"), note=f"Pinned by engcrm; Maps place {distance}.")
    if pin is None:
        return "no such organization"
    with db() as conn:
        conn.cursor().execute(
            """UPDATE contacts SET address = COALESCE(NULLIF(address, ''), %s),
                   phone = COALESCE(NULLIF(phone, ''), %s), website = COALESCE(NULLIF(website, ''), %s),
                   longitude = CASE WHEN latitude IS NULL THEN %s ELSE longitude END,
                   latitude = COALESCE(latitude, %s), updated_at = NOW()
               WHERE id = %s""",
            (result.get("address"), result.get("phone"), result.get("website"),
             result.get("lon"), result.get("lat"), result["id"]),
        )
    log_audit(None, None, "contact.filled_from_maps", f"contact:{result['id']}", "blank fields only")
    return "pinned"


def dropped_but_pinned(workspace_id: int, list_name: str = COLD_CALL_CANDIDATES) -> list[dict]:
    """Organizations the scout dropped (consulting deal out of the pipeline) that are still
    pinned on `list_name`: shown after a Judge run. The pins stay unless Chris asks."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT DISTINCT c.id, c.name, c.city
              FROM contacts c
              JOIN deals d ON d.contact_id = c.id AND d.deleted_at IS NULL
                          AND d.offer_id = offer_id_for(c.workspace_id, 'consulting')
              JOIN map_pins p ON p.contact_id = c.id AND p.list_name = %s AND p.removed_at IS NULL
             WHERE c.workspace_id = %s AND c.deleted_at IS NULL AND d.pipeline_stage = 'not_in_pipeline'
             ORDER BY c.name, c.id
            """,
            (list_name, workspace_id),
        )
        return [dict(row) for row in cur.fetchall()]
