"""Booking setup in the database: settings, appointment types, open hours, blocks, personal links.

Every function runs in the caller's workspace (row security). ensure_booking_defaults() is
idempotent: it fills in only what is missing, so it is safe on every page load.
"""
import hashlib
import secrets
from datetime import datetime, time

from gcrm.api.security import decrypt_private, encrypt_private
from gcrm.config import ACCOUNT_ENCRYPTION_KEY
from gcrm.db.connection import db

# kind -> (minutes, travel minutes, needs approval). Custom's minutes is its shortest choice.
DEFAULT_TYPES = {"call": (15, 0, False), "video": (45, 0, False), "visit": (60, 60, False), "custom": (30, 0, True)}
CUSTOM_LENGTHS = (30, 60, 90, 120)
# Monday to Friday, 09:30-12:00 and 13:30-16:30 (Chris's rough hours, 2026-11-28).
DEFAULT_HOURS = [(weekday, opens, closes) for weekday in range(5)
                 for opens, closes in ((time(9, 30), time(12)), (time(13, 30), time(16, 30)))]
SETTING_FIELDS = ("is_enabled", "public_slug", "organizer_email", "organizer_name", "host_email", "room_link",
                  "min_notice_hours", "horizon_days", "gap_minutes", "cancel_cutoff_hours")


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_token() -> tuple[str, str]:
    """A random URL-safe token and its hash; only the hash is used for lookups."""
    token = secrets.token_urlsafe(32)
    return token, hash_token(token)


def ensure_booking_defaults() -> None:
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("INSERT INTO booking_settings DEFAULT VALUES "
                       "ON CONFLICT (workspace_id) DO NOTHING RETURNING workspace_id")
        is_new_workspace = cursor.fetchone() is not None
        for kind, (minutes, travel, needs_approval) in DEFAULT_TYPES.items():
            cursor.execute("INSERT INTO booking_types (kind, minutes, travel_minutes, needs_approval) "
                           "VALUES (%s, %s, %s, %s) ON CONFLICT (workspace_id, kind) DO NOTHING",
                           (kind, minutes, travel, needs_approval))
        if is_new_workspace:
            cursor.executemany("INSERT INTO booking_hours (weekday, opens, closes) VALUES (%s, %s, %s)",
                               DEFAULT_HOURS)


def workspace_for_slug(slug: str) -> int | None:
    """The workspace of an enabled public booking page. Runs before any workspace is set."""
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT workspace_id FROM booking_settings WHERE public_slug=%s AND is_enabled", (slug,))
        row = cursor.fetchone()
    return row["workspace_id"] if row else None


def get_booking_settings() -> dict:
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT * FROM booking_settings")
        settings = dict(cursor.fetchone())
    encrypted = settings.pop("feed_url_encrypted")
    settings["feed_url"] = decrypt_private(encrypted, ACCOUNT_ENCRYPTION_KEY) if encrypted else ""
    return settings


def update_booking_settings(changes: dict) -> None:
    """Save the given fields. `feed_url` is encrypted; an empty one clears it."""
    columns = {key: value for key, value in changes.items() if key in SETTING_FIELDS}
    if "feed_url" in changes:
        url = changes["feed_url"].strip()
        columns["feed_url_encrypted"] = encrypt_private(url, ACCOUNT_ENCRYPTION_KEY) if url else None
    if not columns:
        return
    assignments = ", ".join(f"{column}=%s" for column in columns)  # names come from SETTING_FIELDS only
    with db() as connection:
        connection.cursor().execute(f"UPDATE booking_settings SET {assignments}, updated_at=NOW()",
                                    tuple(columns.values()))


def list_booking_types() -> list[dict]:
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT * FROM booking_types ORDER BY array_position(ARRAY['call','video','visit','custom'], kind)")
        return [dict(row) for row in cursor.fetchall()]


def update_booking_type(kind: str, *, minutes: int, travel_minutes: int, weekdays: list[int] | None,
                        is_active: bool) -> None:
    with db() as connection:
        connection.cursor().execute(
            "UPDATE booking_types SET minutes=%s, travel_minutes=%s, weekdays=%s, is_active=%s WHERE kind=%s",
            (minutes, travel_minutes, weekdays, is_active, kind))


def list_booking_hours() -> list[dict]:
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT weekday, opens, closes FROM booking_hours ORDER BY weekday, opens")
        return [dict(row) for row in cursor.fetchall()]


def replace_booking_hours(hours: list[tuple[int, time, time]]) -> None:
    """Replace the whole week at once, so a half-saved week cannot exist."""
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("DELETE FROM booking_hours")
        cursor.executemany("INSERT INTO booking_hours (weekday, opens, closes) VALUES (%s, %s, %s)", hours)


def add_booking_block(starts_at: datetime, ends_at: datetime, note: str) -> int:
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("INSERT INTO booking_blocks (starts_at, ends_at, note) VALUES (%s, %s, %s) RETURNING id",
                       (starts_at, ends_at, note.strip()[:200]))
        return cursor.fetchone()["id"]


def list_upcoming_blocks(now: datetime) -> list[dict]:
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT * FROM booking_blocks WHERE ends_at > %s ORDER BY starts_at", (now,))
        return [dict(row) for row in cursor.fetchall()]


def delete_booking_block(block_id: int) -> None:
    with db() as connection:
        connection.cursor().execute("DELETE FROM booking_blocks WHERE id=%s", (block_id,))


def create_booking_link(label: str, *, contact_id: int | None, person_id: int | None,
                        deal_id: int | None) -> str:
    """A personal link for one organization or person. Returns the token for the URL."""
    token, token_hash = new_token()
    with db() as connection:
        connection.cursor().execute(
            "INSERT INTO booking_links (token_hash, token_encrypted, label, contact_id, person_id, deal_id) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (token_hash, encrypt_private(token, ACCOUNT_ENCRYPTION_KEY), label.strip(), contact_id, person_id, deal_id))
    return token


def list_booking_links() -> list[dict]:
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT * FROM booking_links WHERE is_active ORDER BY created_at DESC")
        links = [dict(row) for row in cursor.fetchall()]
    for link in links:
        link["token"] = decrypt_private(link.pop("token_encrypted"), ACCOUNT_ENCRYPTION_KEY)
    return links


def booking_link_for_token(token: str) -> dict | None:
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id, contact_id, person_id, deal_id, kinds FROM booking_links "
                       "WHERE token_hash=%s AND is_active", (hash_token(token),))
        row = cursor.fetchone()
    return dict(row) if row else None


def retire_booking_link(link_id: int) -> None:
    with db() as connection:
        connection.cursor().execute("UPDATE booking_links SET is_active=FALSE WHERE id=%s", (link_id,))
