"""Field tools: what Claude does for Chris on the road, through the remote MCP connector.

"I'm standing outside this place, the owner is Maria, friendly, call back in two weeks":
Claude reads where he is (the phone's field mode), asks Google what is there, saves the
organization and the person, logs the first contact, and reads back what it saved.

Every function takes the caller (`FieldUser`: the token's user and workspace) and uses
the same write helpers as the web and the phone, so the rules (duplicates, limits,
allowed values, audit log) stay in one place. Everything saved is journalled in
`mcp_actions`, so `undo_last` can take the newest change back.
See docs/plans/2026-11-03-field-mode-and-remote-mcp-plan.md.
"""
from dataclasses import dataclass
from datetime import date

from psycopg2.extras import Json

from gcrm.activity_types import (
    ATTITUDES,
    MY_READS,
    ORGANIZATION_METHODS,
    PERSON_METHODS,
    parse_choices,
    parse_minutes,
    parse_occurred_on,
)
from gcrm.dates import parse_day
from gcrm.db.connection import db
from gcrm.sources import CLAUDE_FIELD
from gcrm.tools.db_audit import log_audit
from gcrm.tools.db_interactions import delete_meeting_note, log_meeting_note
from gcrm.tools.db_organizations import save_organization
from gcrm.tools.db_people import find_existing_person, save_person, set_person_rating
from gcrm.tools.db_people_interactions import delete_person_interaction, log_person_note
from gcrm.tools.db_personal_priorities import set_organization_rating
from gcrm.tools.deal_records import get_deal, get_deals, resolve_log_offer, set_deal_next_step
from gcrm.tools.field_locations import latest_point
from gcrm.tools.search import PlacesUnavailable, places_nearby, reverse_geocode


@dataclass(frozen=True)
class FieldUser:
    user_id: int
    workspace_id: int


class FieldError(ValueError):
    """Something Claude should say back as it is: a refusal, never a crash."""


# The activity kinds Claude may name, in the words of each vocabulary.
_ORGANIZATION_KIND = {"drop_in": "in_person", "meeting": "meeting", "phone": "phone", "video": "video",
                      "email": "email", "post_mail": "letter", "note": None}
_PERSON_KIND = {"drop_in": "visit", "meeting": "meeting", "phone": "call", "video": "video",
                "email": "email", "post_mail": "letter", "note": None}
KINDS = tuple(_ORGANIZATION_KIND)
assert set(_ORGANIZATION_KIND.values()) - {None} <= set(ORGANIZATION_METHODS)
assert set(_PERSON_KIND.values()) - {None} <= set(PERSON_METHODS)


# --- where am I ------------------------------------------------------------------

def _here(user: FieldUser) -> dict:
    point = latest_point(user.user_id)
    if point is None:
        raise FieldError("No position yet: switch on Field mode in the EngCRM app (Settings), "
                         "or tell me the address.")
    if point["stale"]:
        minutes = point["age_seconds"] // 60
        raise FieldError(f"The last position is {minutes} minutes old, too old to trust. "
                         "Is Field mode still on? Otherwise tell me the address.")
    return point


def where_am_i(user: FieldUser) -> dict:
    point = _here(user)
    town = reverse_geocode(point["latitude"], point["longitude"])
    return {**point, "town": town["name"] if town else None}


def businesses_here(user: FieldUser, radius_m: int = 60) -> dict:
    point = _here(user)
    radius = min(max(radius_m, 10), 500)
    try:
        places = places_nearby(point["latitude"], point["longitude"], radius_m=radius)
    except PlacesUnavailable:
        raise FieldError("Google Maps could not be asked just now. Tell me the business name instead.")
    known = _known_places(user, places)
    for place in places:
        place["in_engcrm"] = known.get(place["place_id"]) or known.get((place["name"].lower(), place["city"].lower()))
    return {"position_accuracy_m": point["accuracy_m"], "radius_m": radius, "businesses": places}


def _known_places(user: FieldUser, places: list[dict]) -> dict:
    """Which of these places are organizations already, by Google place id or name+city."""
    if not places:
        return {}
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, name, city, google_data->>'id' AS place_id FROM contacts "
            "WHERE workspace_id = %s AND deleted_at IS NULL AND ("
            "google_data->>'id' = ANY(%s) OR (lower(name), lower(coalesce(city, ''))) IN "
            "(SELECT * FROM unnest(%s::text[], %s::text[])))",
            (user.workspace_id, [p["place_id"] for p in places if p["place_id"]],
             [p["name"].lower() for p in places], [p["city"].lower() for p in places]),
        )
        rows = cur.fetchall()
    known: dict = {}
    for row in rows:
        entry = {"organization_id": row["id"], "name": row["name"]}
        if row["place_id"]:
            known[row["place_id"]] = entry
        known[(row["name"].lower(), (row["city"] or "").lower())] = entry
    return known


# --- finding ---------------------------------------------------------------------

def find_organization(user: FieldUser, query: str, limit: int = 8) -> list[dict]:
    text = (query or "").strip()
    if not text:
        raise FieldError("Say a name or a town to look for.")
    like = f"%{text}%"
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, name, city, type, address FROM contacts "
            "WHERE workspace_id = %s AND deleted_at IS NULL AND (name ILIKE %s OR city ILIKE %s) "
            "ORDER BY (lower(name) = lower(%s)) DESC, name LIMIT %s",
            (user.workspace_id, like, like, text, min(max(limit, 1), 25)),
        )
        return [dict(row) for row in cur.fetchall()]


def _organization(user: FieldUser, organization_id: int) -> dict:
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, name, city FROM contacts WHERE id = %s AND workspace_id = %s AND deleted_at IS NULL",
                    (organization_id, user.workspace_id))
        row = cur.fetchone()
    if row is None:
        raise FieldError(f"There is no organization #{organization_id} in EngCRM.")
    return dict(row)


def _person(user: FieldUser, person_id: int) -> dict:
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, name FROM people WHERE id = %s AND workspace_id = %s AND deleted_at IS NULL",
                    (person_id, user.workspace_id))
        row = cur.fetchone()
    if row is None:
        raise FieldError(f"There is no person #{person_id} in EngCRM.")
    return dict(row)


# --- saving ----------------------------------------------------------------------

def _journal(user: FieldUser, kind: str, target_id: int, summary: str,
             owner_id: int | None = None, before: dict | None = None) -> None:
    with db() as conn:
        conn.cursor().execute(
            "INSERT INTO mcp_actions (user_id, kind, target_id, owner_id, before, summary) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (user.user_id, kind, target_id, owner_id, Json(before) if before is not None else None, summary),
        )
    # Every save through the connector, uniformly; the actor is the remote MCP's audit scope.
    log_audit(None, None, f"mcp.{kind}", f"{kind.split('_')[0]}:{target_id}", summary[:200])


def add_organization(user: FieldUser, name: str, city: str = "", address: str = "", type: str = "",
                     place_id: str = "", latitude: float | None = None, longitude: float | None = None,
                     notes: str = "", country: str = "DE") -> dict:
    """Save a business, usually one businesses_here found (pass its place_id, address
    and coordinates along). An existing one is reported, not duplicated."""
    name, city = (name or "").strip(), (city or "").strip()
    if not name:
        raise FieldError("An organization needs a name.")
    if len(name) > 200 or len(city) > 100 or len(type) > 60 or len(address) > 500:
        raise FieldError("Name, town, type or address is too long.")
    google = None
    if place_id:
        google = {"id": place_id, "formattedAddress": address, "latitude": latitude, "longitude": longitude}
    organization_id = save_organization(
        name, city, source=CLAUDE_FIELD, country=(country or "DE")[:2].upper(), type=type.strip(),
        notes=(notes or "").strip(), latitude=latitude, longitude=longitude, google=google,
    )
    if not organization_id:
        existing = find_organization(user, name, limit=3)
        same = next((o for o in existing if o["name"].lower() == name.lower()), None)
        if same:
            return {"saved": False, "already_there": same,
                    "said": f"{same['name']} is already in EngCRM (#{same['id']}); nothing new saved."}
        raise FieldError(f"{name} was not added: it matches an existing record or the blocked-chains list.")
    if address:
        with db() as conn:
            conn.cursor().execute("UPDATE contacts SET address = %s WHERE id = %s", (address.strip(), organization_id))
    said = f"Saved {name}" + (f", {address}" if address else (f", {city}" if city else "")) + f" (#{organization_id})."
    _journal(user, "organization_added", organization_id, said)
    return {"saved": True, "organization_id": organization_id, "said": said}


def add_person(user: FieldUser, organization_id: int, name: str, title: str = "", email: str = "",
               phone: str = "", notes: str = "", met_at: str = "") -> dict:
    """A person met at an organization. An existing one is reported, not duplicated."""
    organization = _organization(user, organization_id)
    name = (name or "").strip()
    if not name:
        raise FieldError("A person needs a name.")
    with db() as conn:
        existing = find_existing_person(conn.cursor(), name, (email or "").strip(), organization_id)
    if existing:
        return {"saved": False, "person_id": existing,
                "said": f"{name} at {organization['name']} is already in EngCRM (#{existing}); nothing new saved."}
    person_id = save_person(
        name, source=CLAUDE_FIELD, title=(title or "").strip(), email=(email or "").strip(),
        phone=(phone or "").strip(), notes=(notes or "").strip(), met_at=(met_at or "").strip(),
        city=organization["city"] or "", contact_id=organization_id,
    )
    said = f"Saved {name}" + (f", {title}" if title else "") + f" at {organization['name']} (#{person_id})."
    _journal(user, "person_added", person_id, said)
    return {"saved": True, "person_id": person_id, "said": said}


def log_activity(user: FieldUser, note: str, organization_id: int | None = None, person_id: int | None = None,
                 kind: str = "drop_in", minutes: int | None = None, attitude: list[str] | None = None,
                 my_read: list[str] | None = None, materials_left: str = "", follow_up_promised: str = "",
                 follow_up_date: str = "", offer: str | None = None, occurred_on: str = "") -> dict:
    """Log what happened, on an organization or a person (exactly one), with the same
    fields as Log activity on the web."""
    if (organization_id is None) == (person_id is None):
        raise FieldError("Log on one organization or one person.")
    if not (note or "").strip():
        raise FieldError("Say what happened.")
    if kind not in KINDS:
        raise FieldError(f"The kind is one of: {', '.join(KINDS)}.")
    try:
        duration = parse_minutes(minutes)
        attitudes, reads = parse_choices(attitude or [], ATTITUDES), parse_choices(my_read or [], MY_READS)
        day = parse_occurred_on(occurred_on)
        follow_up = parse_day(follow_up_date) if follow_up_date else None
    except ValueError as error:
        raise FieldError(f"Not saved: {error}. Attitudes: {', '.join(ATTITUDES)}; reads: {', '.join(MY_READS)}.")
    if organization_id is not None:
        organization = _organization(user, organization_id)
        try:
            offer_id = resolve_log_offer("organization", organization_id, offer, user.workspace_id)
        except ValueError:
            raise FieldError(f"There is no offer called {offer}.")
        note_id = log_meeting_note(
            organization_id, _ORGANIZATION_KIND[kind], note.strip(), follow_up_date=follow_up,
            follow_up_text=follow_up_promised.strip() or None, duration_minutes=duration, offer_id=offer_id,
            occurred_on=day, attitude=attitudes, my_read=reads, materials_left=materials_left.strip() or None)
        said = f"Logged a {kind.replace('_', '-')} at {organization['name']}"
        journal_kind, owner = "organization_activity", organization_id
    else:
        person = _person(user, person_id)
        if day or materials_left or follow_up_promised or follow_up_date:
            raise FieldError("A person's activity takes no date, materials or follow-up: log those on "
                             "their organization, or set a next step.")
        try:
            offer_id = resolve_log_offer("person", person_id, offer, user.workspace_id)
        except ValueError:
            raise FieldError(f"There is no offer called {offer}.")
        note_id = log_person_note(person_id, _PERSON_KIND[kind], note.strip(), duration_minutes=duration,
                                  offer_id=offer_id, attitude=attitudes, my_read=reads)
        said = f"Logged a {kind.replace('_', '-')} with {person['name']}"
        journal_kind, owner = "person_activity", person_id
    if follow_up_promised or follow_up:
        said += "; follow-up" + (f" {follow_up_promised.strip()}" if follow_up_promised else "") + (
            f" on {follow_up.strftime('%d.%m.%Y')}" if follow_up else "")
    said += "."
    _journal(user, journal_kind, note_id, said, owner_id=owner)
    return {"saved": True, "activity_id": note_id, "said": said}


def set_next_step(user: FieldUser, step: str, due: str = "", organization_id: int | None = None,
                  person_id: int | None = None, offer: str = "") -> dict:
    """What happens next on a deal of an organization or person (one of them). With
    several deals, `offer` (its slug) says which."""
    if (organization_id is None) == (person_id is None):
        raise FieldError("Set the next step on one organization or one person.")
    owner, owner_id = ("organization", organization_id) if organization_id is not None else ("person", person_id)
    (_organization if owner == "organization" else _person)(user, owner_id)
    deals = get_deals(owner, owner_id, user.workspace_id)
    if offer:
        deals = [d for d in deals if d["offer_slug"] == offer]
    if len(deals) != 1:
        names = ", ".join(d["offer_slug"] for d in get_deals(owner, owner_id, user.workspace_id)) or "none"
        raise FieldError(f"Say which offer the next step is for (its deals: {names}).")
    deal = deals[0]
    try:
        when = parse_day(due) if due else None
        result = set_deal_next_step(deal["id"], step, when, user.workspace_id)
    except ValueError as error:
        raise FieldError(f"Not saved: {error}.")
    said = f"Next step on {deal['offer_name']}: {result['next_step'] or 'cleared'}" + (
        f", by {when.strftime('%d.%m.%Y')}" if when else "") + "."
    _journal(user, "next_step", deal["id"], said,
             before={"next_step": deal["next_step"], "next_step_date": deal["next_step_date"]})
    return {"saved": True, "said": said}


_RATINGS = ("priority", "short_term_value", "long_term_value")


def set_ratings(user: FieldUser, organization_id: int | None = None, person_id: int | None = None,
                priority: int | None = None, short_term_value: int | None = None,
                long_term_value: int | None = None) -> dict:
    """Private ratings: priority 1 (best) to 6 (forget it) on an organization, 1 to 5 on a
    person; short- and long-term value 3 high, 2 medium, 1 low, 0 zero. Only those given change."""
    if (organization_id is None) == (person_id is None):
        raise FieldError("Rate one organization or one person.")
    wanted = {k: v for k, v in zip(_RATINGS, (priority, short_term_value, long_term_value)) if v is not None}
    if not wanted:
        raise FieldError("Give a priority, a short-term or a long-term value.")
    if person_id is not None and wanted.get("priority") == 6:
        raise FieldError("A person's rating goes from 1 to 5.")
    owner_id = organization_id if organization_id is not None else person_id
    record = (_organization if organization_id is not None else _person)(user, owner_id)
    before = _current_ratings(user, organization_id, person_id)
    setter = set_organization_rating if organization_id is not None else set_person_rating
    try:
        for rating, value in wanted.items():
            setter(user.user_id, user.workspace_id, owner_id, rating, value)
    except ValueError as error:
        raise FieldError(f"Not saved: {error}.")
    said = f"Rated {record['name']}: " + ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in wanted.items()) + "."
    _journal(user, "organization_ratings" if organization_id is not None else "person_ratings", owner_id, said,
             before=before)
    return {"saved": True, "said": said}


def _current_ratings(user: FieldUser, organization_id: int | None, person_id: int | None) -> dict:
    table, column, owner = (("contact_user_priorities", "contact_id", organization_id) if organization_id is not None
                            else ("person_user_priorities", "person_id", person_id))
    with db() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT priority, short_term_value, long_term_value FROM {table} "  # names are constants
                    f"WHERE user_id = %s AND {column} = %s", (user.user_id, owner))
        row = cur.fetchone()
    return dict(row) if row else {rating: None for rating in _RATINGS}


# --- undo ------------------------------------------------------------------------

def undo_last(user: FieldUser) -> dict:
    """Take back the newest thing this connector saved for this user."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM mcp_actions WHERE user_id = %s AND undone_at IS NULL ORDER BY id DESC LIMIT 1",
                    (user.user_id,))
        action = cur.fetchone()
    if action is None:
        raise FieldError("There is nothing of mine left to undo.")
    kind, target = action["kind"], action["target_id"]
    if kind == "organization_added":
        with db() as conn:
            conn.cursor().execute("UPDATE contacts SET deleted_at = NOW() WHERE id = %s AND workspace_id = %s",
                                  (target, user.workspace_id))
    elif kind == "person_added":
        with db() as conn:
            conn.cursor().execute("UPDATE people SET deleted_at = NOW() WHERE id = %s AND workspace_id = %s",
                                  (target, user.workspace_id))
    elif kind == "organization_activity":
        delete_meeting_note(action["owner_id"], target)
    elif kind == "person_activity":
        delete_person_interaction(action["owner_id"], target)
    elif kind == "next_step":
        before = action["before"] or {}
        with db() as conn:
            deal = get_deal(conn.cursor(), target, user.workspace_id)
        previous_date = date.fromisoformat(before["next_step_date"]) if before.get("next_step_date") else None
        set_deal_next_step(deal["id"], before.get("next_step") or "", previous_date, user.workspace_id)
    else:  # ratings
        before = action["before"] or {}
        setter = set_organization_rating if kind == "organization_ratings" else set_person_rating
        for rating in _RATINGS:
            setter(user.user_id, user.workspace_id, target, rating, before.get(rating))
    with db() as conn:
        conn.cursor().execute("UPDATE mcp_actions SET undone_at = NOW() WHERE id = %s", (action["id"],))
    log_audit(None, None, "mcp.undo", f"mcp_action:{action['id']}", kind)
    return {"undone": True, "said": f"Undone: {action['summary']}"}
