"""A workspace's whole CRM as a ZIP of CSV files — the customer's own copy of their data.

One CSV per kind of record, UTF-8 with a BOM (Excel then reads umlauts right), comma
separated, ISO dates. Every row keeps its stable `id`, and related rows carry both the id
and the readable name, so each file makes sense alone and joins in any spreadsheet.

Isolation: `build_backup` enters the workspace's scope itself, so the database's row
security applies, and every query also filters on the workspace explicitly. Never exported:
password hashes, sessions, tokens, MFA secrets, the audit log, AI keys, raw map data and
business-card photos. Soft-deleted rows are left out.
"""
import csv
import io
import json
import zipfile
from datetime import date, datetime, timezone
from decimal import Decimal

from gcrm.db.connection import db
from gcrm.workspace_context import workspace_scope

FORMAT_VERSION = 1

_SIGN_THEN_SAFE = "0123456789 .,"

# filename -> SQL. `%(ws)s` is the workspace id. Deleted records are filtered here, not later.
FILES: dict[str, str] = {
    "organizations.csv": """
        SELECT id, name, type, subtype, address, city, country, website, email, phone,
               linkedin_url, xing_url, preferred_language, source, do_not_contact, starred,
               notes, created_at, updated_at
          FROM contacts WHERE workspace_id = %(ws)s AND deleted_at IS NULL ORDER BY id""",
    "people.csv": """
        SELECT p.id, p.name, p.title, p.email, p.phone, p.website, p.city, p.country,
               p.linkedin_url, p.xing_url, p.relationship,
               c.id AS organization_id, c.name AS organization_name,
               p.met_at, p.preferred_language, p.source, p.notes, p.created_at, p.updated_at
          FROM people p LEFT JOIN contacts c ON c.id = p.contact_id AND c.deleted_at IS NULL
         WHERE p.workspace_id = %(ws)s AND p.deleted_at IS NULL ORDER BY p.id""",
    "activities.csv": """
        SELECT 'organization' AS kind, i.id, c.id AS organization_id, c.name AS organization_name,
               NULL::int AS person_id, NULL::text AS person_name,
               i.interaction_date AS date, i.method::text AS method, i.direction::text AS direction,
               i.summary AS summary, i.outcome::text AS outcome, i.next_action::text AS next_action,
               i.next_action_date AS next_action_date, i.duration_minutes, o.name AS offer
          FROM interactions i
          JOIN contacts c ON c.id = i.contact_id AND c.deleted_at IS NULL AND c.workspace_id = %(ws)s
          LEFT JOIN offers o ON o.id = i.offer_id
         WHERE i.workspace_id = %(ws)s AND i.deleted_at IS NULL
        UNION ALL
        SELECT 'person', pi.id, c.id, c.name, p.id, p.name,
               pi.occurred_at::date, pi.method::text, NULL::text,
               pi.note, NULL::text, NULL::text, NULL::date, pi.duration_minutes, o.name
          FROM people_interactions pi
          JOIN people p ON p.id = pi.person_id AND p.deleted_at IS NULL AND p.workspace_id = %(ws)s
          LEFT JOIN contacts c ON c.id = p.contact_id AND c.deleted_at IS NULL
          LEFT JOIN offers o ON o.id = pi.offer_id
         WHERE pi.deleted_at IS NULL
        ORDER BY 1, 2""",
    "deals.csv": """
        SELECT d.id, o.name AS offer, c.id AS organization_id, c.name AS organization_name,
               p.id AS person_id, p.name AS person_name, d.pipeline_stage, d.status,
               d.next_step, d.next_step_date, d.notes, d.created_at, d.updated_at
          FROM deals d JOIN offers o ON o.id = d.offer_id
          LEFT JOIN contacts c ON c.id = d.contact_id LEFT JOIN people p ON p.id = d.person_id
         WHERE d.workspace_id = %(ws)s AND d.deleted_at IS NULL
           AND COALESCE(c.deleted_at, p.deleted_at) IS NULL ORDER BY d.id""",
    "sales.csv": """
        SELECT s.id, s.deal_id, o.name AS offer, c.id AS organization_id, p.id AS person_id,
               COALESCE(c.name, p.name) AS owner_name, s.amount_eur, s.status,
               s.won_on, s.expected_on, s.collected_on, s.hours, s.description,
               s.series_id::text AS contract_id, s.series_part AS payment_number, s.series_total AS payments_in_contract,
               s.created_at
          FROM sales s JOIN deals d ON d.id = s.deal_id AND d.deleted_at IS NULL
          JOIN offers o ON o.id = d.offer_id
          LEFT JOIN contacts c ON c.id = d.contact_id LEFT JOIN people p ON p.id = d.person_id
         WHERE s.workspace_id = %(ws)s AND s.deleted_at IS NULL
           AND COALESCE(c.deleted_at, p.deleted_at) IS NULL ORDER BY s.id""",
    "subscriptions.csv": """
        SELECT s.id, s.deal_id, o.name AS offer, c.id AS organization_id, p.id AS person_id,
               COALESCE(c.name, p.name) AS owner_name, s.amount_eur_month,
               s.started_on, s.ended_on, s.note, s.created_at
          FROM subscriptions s JOIN deals d ON d.id = s.deal_id AND d.deleted_at IS NULL
          JOIN offers o ON o.id = d.offer_id
          LEFT JOIN contacts c ON c.id = d.contact_id LEFT JOIN people p ON p.id = d.person_id
         WHERE s.workspace_id = %(ws)s AND s.deleted_at IS NULL
           AND COALESCE(c.deleted_at, p.deleted_at) IS NULL ORDER BY s.id""",
    "income_plan.csv": """
        SELECT monthly_need, expected_new_monthly, expected_new_months, expected_new_delay, expected_new_campaign, expected_new_hours_per_week, expected_new_rate, start_month, updated_at FROM income_plan WHERE workspace_id = %(ws)s""",
    "other_income.csv": """
        SELECT id, label, amount_eur, first_received_on, covers_from, payments, confirmed, created_at
          FROM other_income WHERE workspace_id = %(ws)s AND deleted_at IS NULL ORDER BY id""",
    "offers.csv": """
        SELECT id, slug, name, website, revenue_kind, sort_order, archived_at
          FROM offers WHERE workspace_id = %(ws)s ORDER BY sort_order, id""",
}

README = """EngCRM data backup
==================

Exported {exported_at} (UTC), workspace {workspace_id}. Format version {version}.

Files (CSV, UTF-8, comma separated, dates as YYYY-MM-DD):
  organizations.csv   companies, clinics, schools and other organizations
  people.csv          people, with their organization when they have one
  activities.csv      calls, visits, emails and notes (kind = organization or person)
  deals.csv           what you pitch to each organization or person, and where it stands
  sales.csv           sales; status is expected, booked, contracted, collected or cancelled. A contract paid in
                      monthly payments is one row per payment, tied by contract_id (payment_number of
                      payments_in_contract); expected_on is the day that payment is due; hours is the work
                      in that payment (empty: not recorded)
  subscriptions.csv   recurring revenue per deal
  offers.csv          what you sell
  income_plan.csv     the income you need per month from sales, the first month it applies from, and the new
                      sales you expect to book each month (expected_new_monthly) and how many months each
                      booking pays (expected_new_months; empty: for ever), and the months
                      from booking to first payment (expected_new_delay) and how many months the
                      campaign runs (expected_new_campaign; empty: it never stops); the monthly value is
                      worked out from expected_new_hours_per_week x expected_new_rate x 52 / 12
  other_income.csv    other income that covers part of it: the months it covers, and whether it is confirmed
  manifest.json       when this was made and how many rows each file holds

Every row has a stable `id`. Related rows carry the id and the name, e.g. people.csv has
organization_id and organization_name, so you can join the files in any spreadsheet or map
them to another CRM's import format.

Not included, on purpose: passwords, sessions, tokens, the audit log and business-card photos.
Deleted records are not included.

A cell that begins with = or @ (or a sign followed by a letter) starts with an apostrophe
in these files, so a spreadsheet shows the text instead of running it as a formula.
"""


def neutralize_formula(value) -> str:
    """The cell text, made safe to open in a spreadsheet. Text that a spreadsheet would
    run as a formula gets a leading apostrophe; numbers and phone numbers are left alone."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    text = str(value)
    if not text:
        return ""
    if text[0] in "=@\t\r":
        return "'" + text
    if text[0] in "+-" and len(text) > 1 and text[1] not in _SIGN_THEN_SAFE:
        return "'" + text
    return text


def _csv_bytes(columns: list[str], rows: list[list]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(columns)
    for row in rows:
        writer.writerow([neutralize_formula(cell) for cell in row])
    return b"\xef\xbb\xbf" + buffer.getvalue().encode("utf-8")


def build_backup(workspace_id: int, now: datetime | None = None) -> tuple[bytes, dict]:
    """The workspace's ZIP and its manifest. Raises on any database error: a backup that
    is silently incomplete is worse than none."""
    exported_at = (now or datetime.now(timezone.utc)).replace(microsecond=0)
    files: dict[str, bytes] = {}
    counts: dict[str, int] = {}
    with workspace_scope(workspace_id):
        with db() as connection:
            cursor = connection.cursor()
            for name, sql in FILES.items():
                cursor.execute(sql, {"ws": workspace_id})
                columns = [column[0] for column in cursor.description]
                rows = [list(row.values()) if isinstance(row, dict) else list(row) for row in cursor.fetchall()]
                files[name] = _csv_bytes(columns, rows)
                counts[name] = len(rows)
    manifest = {"app": "EngCRM", "format_version": FORMAT_VERSION, "workspace_id": workspace_id,
                "exported_at": exported_at.isoformat(), "counts": counts}
    readme = README.format(exported_at=exported_at.isoformat(), workspace_id=workspace_id, version=FORMAT_VERSION)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
        archive.writestr("README.txt", readme)
        archive.writestr("manifest.json", json.dumps(manifest, indent=2))
    return buffer.getvalue(), manifest
