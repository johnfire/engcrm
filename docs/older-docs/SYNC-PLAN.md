# eng-crm Sync Plan

# Source: art-crm/artcrm-supervisor (April 2026)

This plan brings eng-crm up to date with improvements made in art-crm.
Execute every step in order. Do not skip migrations.
All file paths are relative to `~/programming/eng-crm/`.

---

## 0. Context

- Package root is `gcrm/`
- Imports use `from gcrm.x`
- Config comes from `gcrm/vertical.py` — **do not change any existing keys**
- This CRM is for marketing Christopher's AI engineering & consulting business
- After this sync, eng-crm gets its own interview agent: `engcrm-interview-agent/`
- Interview command will be: `engcrm-interview`

---

## Step 1 — Database migrations

Check which migrations have already been applied. The eng-crm DB already has migrations
000_a through 006. Create and run only the missing ones:

### `007_enriched_at.sql`

```sql
ALTER TABLE contacts ADD COLUMN IF NOT EXISTS enriched_at TIMESTAMPTZ;
```

### `008_contact_field_notes.sql`

```sql
ALTER TABLE contacts
    ADD COLUMN IF NOT EXISTS access_notes             text,
    ADD COLUMN IF NOT EXISTS visit_duration           varchar(100),
    ADD COLUMN IF NOT EXISTS decision_maker           varchar(200),
    ADD COLUMN IF NOT EXISTS first_impression         varchar(20),
    ADD COLUMN IF NOT EXISTS last_impression          varchar(20),
    ADD COLUMN IF NOT EXISTS price_sensitivity        text,
    ADD COLUMN IF NOT EXISTS space_notes              text,
    ADD COLUMN IF NOT EXISTS preferred_contact_method varchar(60),
    ADD COLUMN IF NOT EXISTS last_visited_at          date,
    ADD COLUMN IF NOT EXISTS materials_left           text,
    ADD COLUMN IF NOT EXISTS followup_promised        text;
```

### `009_scan_level.sql`

```sql
ALTER TABLE contacts ADD COLUMN IF NOT EXISTS scan_level int;
```

---

## Step 2 — Update `vertical.py`

Add these two keys to `gcrm/vertical.py` at the bottom. Do not change any existing keys.

```python
# Interview agent — post-visit debrief configuration
INTERVIEW_APP_NAME = "EngCRM"
INTERVIEW_MATERIALS_OPTIONS = [
    "business card",
    "one-pager",
    "demo link",
    "proposal",
    "case study",
    "Förderung info sheet",
    "nothing",
]
```

---

## Step 3 — Update `gcrm/api/routers/contacts.py`

Replace the entire file. Key changes vs current:

- Added `type` filter
- Added `has_contact` filter
- Added `contact_detail` GET route
- Added `contact_edit` POST route
- Added `contact_brief` GET route
- Added `contact_print` GET route
- Fixed interaction history query (`interaction_type`/`notes` → `method`/`summary`)
- Added `urlenc` Jinja filter

```python
from fastapi import APIRouter, Request, Query, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from urllib.parse import quote_plus
from typing import Optional
from gcrm.db.connection import db

router = APIRouter(prefix="/contacts", tags=["contacts"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent.parent / "ui" / "templates"))
templates.env.filters["urlenc"] = quote_plus

VALID_STATUSES = (
    "candidate", "cold", "contacted", "meeting", "proposal",
    "accepted", "rejected", "dormant", "on_hold", "dropped", "do_not_contact",
    "networking_visit", "bad_email",
)

PAGE_SIZE = 100

SORT_COLUMNS = {
    "id":           "c.id",
    "name":         "lower(c.name)",
    "city":         "lower(c.city)",
    "type":         "lower(c.type)",
    "status":       "c.status",
    "fit":          "c.fit_score",
    "last_contact": "MAX(i.interaction_date)",
}


@router.get("/", response_class=HTMLResponse)
def contact_list(
    request: Request,
    status: str = Query(default=""),
    type: str = Query(default=""),
    q: str = Query(default=""),
    has_contact: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    sort: str = Query(default="id"),
    dir: str = Query(default="asc"),
):
    offset = (page - 1) * PAGE_SIZE
    sort_col = SORT_COLUMNS.get(sort, "c.id")
    sort_dir = "DESC" if dir == "desc" else "ASC"

    with db() as conn:
        cur = conn.cursor()

        conditions = []
        params = []
        if status:
            conditions.append("c.status = %s")
            params.append(status)
        if type:
            conditions.append("lower(c.type) = lower(%s)")
            params.append(type)
        if q:
            conditions.append("(lower(c.name) LIKE %s OR lower(c.city) LIKE %s)")
            params += [f"%{q.lower()}%", f"%{q.lower()}%"]
        if has_contact == "1":
            conditions.append("c.id IN (SELECT DISTINCT contact_id FROM interactions)")
        elif has_contact == "0":
            conditions.append("c.id NOT IN (SELECT DISTINCT contact_id FROM interactions)")

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        cur.execute(
            f"SELECT COUNT(DISTINCT c.id) AS cnt FROM contacts c {where}",
            params,
        )
        total = cur.fetchone()["cnt"]

        cur.execute(
            f"""
            SELECT
                c.id, c.name, c.city, c.country, c.type, c.status,
                c.email, c.website, c.fit_score, c.notes, c.flagged,
                MAX(i.interaction_date) AS last_contact
            FROM contacts c
            LEFT JOIN interactions i ON i.contact_id = c.id
            {where}
            GROUP BY c.id
            ORDER BY {sort_col} {sort_dir} NULLS LAST
            LIMIT {PAGE_SIZE} OFFSET {offset}
            """,
            params,
        )
        contacts = [dict(r) for r in cur.fetchall()]

        cur.execute("SELECT DISTINCT status FROM contacts WHERE status IS NOT NULL ORDER BY status")
        statuses = [r["status"] for r in cur.fetchall()]

        cur.execute("SELECT DISTINCT type FROM contacts WHERE type IS NOT NULL AND type != '' ORDER BY type")
        types = [r["type"] for r in cur.fetchall()]

    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

    return templates.TemplateResponse("contacts.html", {
        "request": request,
        "contacts": contacts,
        "statuses": statuses,
        "types": types,
        "active_status": status,
        "active_type": type,
        "query": q,
        "has_contact": has_contact,
        "page": page,
        "total_pages": total_pages,
        "total": total,
        "sort": sort,
        "dir": dir,
    })


@router.get("/print", response_class=HTMLResponse)
def contact_print(
    request: Request,
    status: str = Query(default=""),
    type: str = Query(default=""),
    q: str = Query(default=""),
    sort: str = Query(default="id"),
    dir: str = Query(default="asc"),
):
    sort_col = SORT_COLUMNS.get(sort, "c.id")
    sort_dir = "DESC" if dir == "desc" else "ASC"

    with db() as conn:
        cur = conn.cursor()

        conditions = []
        params = []
        if status:
            conditions.append("c.status = %s")
            params.append(status)
        if type:
            conditions.append("lower(c.type) = lower(%s)")
            params.append(type)
        if q:
            conditions.append("(lower(c.name) LIKE %s OR lower(c.city) LIKE %s)")
            params += [f"%{q.lower()}%", f"%{q.lower()}%"]

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        cur.execute(
            f"""
            SELECT
                c.id, c.name, c.city, c.country, c.type, c.status,
                c.email, c.website, c.fit_score, c.notes,
                MAX(i.interaction_date) AS last_contact
            FROM contacts c
            LEFT JOIN interactions i ON i.contact_id = c.id
            {where}
            GROUP BY c.id
            ORDER BY {sort_col} {sort_dir} NULLS LAST
            """,
            params,
        )
        contacts = [dict(r) for r in cur.fetchall()]

    from datetime import date
    active_filters = []
    if status:
        active_filters.append(f"status: {status}")
    if type:
        active_filters.append(f"type: {type}")
    if q:
        active_filters.append(f"search: {q}")

    return templates.TemplateResponse("contacts_print.html", {
        "request": request,
        "contacts": contacts,
        "active_filters": active_filters,
        "total": len(contacts),
        "now": date.today().isoformat(),
    })


@router.get("/{contact_id}/brief", response_class=HTMLResponse)
def contact_brief(contact_id: int, request: Request):
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM contacts WHERE id = %s", (contact_id,))
        contact = dict(cur.fetchone())
        cur.execute(
            "SELECT interaction_date, method, direction, summary, outcome, next_action, next_action_date FROM interactions WHERE contact_id = %s ORDER BY interaction_date DESC LIMIT 5",
            (contact_id,),
        )
        interactions = [dict(r) for r in cur.fetchall()]
    return templates.TemplateResponse("contact_brief.html", {
        "request": request,
        "contact": contact,
        "interactions": interactions,
    })


@router.get("/{contact_id}", response_class=HTMLResponse)
def contact_detail(contact_id: int, request: Request, saved: bool = Query(default=False)):
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM contacts WHERE id = %s", (contact_id,))
        contact = dict(cur.fetchone())
        cur.execute(
            "SELECT interaction_date, method, direction, summary, outcome, next_action, next_action_date FROM interactions WHERE contact_id = %s ORDER BY interaction_date DESC LIMIT 20",
            (contact_id,),
        )
        interactions = [dict(r) for r in cur.fetchall()]
    return templates.TemplateResponse("contact_detail.html", {
        "request": request,
        "contact": contact,
        "interactions": interactions,
        "valid_statuses": VALID_STATUSES,
        "saved": saved,
    })


@router.post("/{contact_id}/edit")
def contact_edit(
    contact_id: int,
    request: Request,
    name: str = Form(""),
    city: str = Form(""),
    country: str = Form(""),
    type: str = Form(""),
    status: str = Form(""),
    fit_score: Optional[str] = Form(None),
    email: str = Form(""),
    phone: str = Form(""),
    website: str = Form(""),
    preferred_contact_method: str = Form(""),
    decision_maker: str = Form(""),
    last_visited_at: Optional[str] = Form(None),
    best_visit_time: str = Form(""),
    visit_duration: str = Form(""),
    first_impression: str = Form(""),
    last_impression: str = Form(""),
    materials_left: str = Form(""),
    followup_promised: str = Form(""),
    access_notes: str = Form(""),
    space_notes: str = Form(""),
    price_sensitivity: str = Form(""),
    notes: str = Form(""),
):
    def empty_none(v):
        return v if v and v.strip() else None

    score = None
    if fit_score and fit_score.strip():
        try:
            score = int(fit_score)
        except ValueError:
            pass

    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE contacts SET
                name = %s, city = %s, country = %s, type = %s, status = %s,
                fit_score = %s, email = %s, phone = %s, website = %s,
                preferred_contact_method = %s, decision_maker = %s,
                last_visited_at = %s, best_visit_time = %s, visit_duration = %s,
                first_impression = %s, last_impression = %s,
                materials_left = %s, followup_promised = %s,
                access_notes = %s, space_notes = %s, price_sensitivity = %s,
                notes = %s, updated_at = NOW()
            WHERE id = %s
            """,
            (
                empty_none(name), empty_none(city), empty_none(country), empty_none(type),
                empty_none(status), score,
                empty_none(email), empty_none(phone), empty_none(website),
                empty_none(preferred_contact_method), empty_none(decision_maker),
                empty_none(last_visited_at), empty_none(best_visit_time), empty_none(visit_duration),
                empty_none(first_impression), empty_none(last_impression),
                empty_none(materials_left), empty_none(followup_promised),
                empty_none(access_notes), empty_none(space_notes), empty_none(price_sensitivity),
                empty_none(notes), contact_id,
            ),
        )
    return RedirectResponse(url=f"/contacts/{contact_id}?saved=1", status_code=303)


@router.post("/{contact_id}/delete")
def delete_contact(contact_id: int, request: Request):
    with db() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM contacts WHERE id = %s", (contact_id,))
    ref = request.headers.get("referer", "/contacts/")
    return RedirectResponse(url=ref, status_code=303)


@router.post("/{contact_id}/unflag")
def unflag_contact(contact_id: int, request: Request):
    with db() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE contacts SET flagged = FALSE WHERE id = %s", (contact_id,))
    ref = request.headers.get("referer", "/contacts/")
    return RedirectResponse(url=ref, status_code=303)
```

---

## Step 4 — Update `gcrm/ui/templates/contacts.html`

Replace the full file:

```html
{% extends "base.html" %} {% block title %}Contacts — EngCRM{% endblock %} {%
block content %}
<div class="page-header">
  <h1>Contacts</h1>
  <span class="muted"
    >{{ total }} total — page {{ page }} of {{ total_pages }}</span
  >
</div>

<form class="filter-bar" method="get" action="/contacts/">
  <input type="hidden" name="sort" value="{{ sort }}" />
  <input type="hidden" name="dir" value="{{ dir }}" />
  <input
    type="text"
    name="q"
    value="{{ query }}"
    placeholder="Search name or city…"
  />
  <select name="status">
    <option value="">All statuses</option>
    {% for s in statuses %}
    <option value="{{ s }}" {% if s="" ="active_status" %}selected{% endif %}>
      {{ s }}
    </option>
    {% endfor %}
  </select>
  <select name="type">
    <option value="">All types</option>
    {% for t in types %}
    <option value="{{ t }}" {% if t="" ="active_type" %}selected{% endif %}>
      {{ t }}
    </option>
    {% endfor %}
  </select>
  <select name="has_contact">
    <option value="" {% if has_contact="" ="" %}selected{% endif %}>
      Any contact date
    </option>
    <option value="1" {% if has_contact="" ="1" %}selected{% endif %}>
      Has contact date
    </option>
    <option value="0" {% if has_contact="" ="0" %}selected{% endif %}>
      No contact date
    </option>
  </select>
  <button type="submit" class="btn-primary">Filter</button>
  {% if query or active_status or active_type or has_contact %}
  <a href="/contacts/" class="muted" style="align-self:center">clear</a>
  {% endif %}
  <a
    href="/contacts/print?status={{ active_status }}&type={{ active_type | urlenc }}&q={{ query | urlenc }}&sort={{ sort }}&dir={{ dir }}"
    target="_blank"
    class="btn-secondary"
    style="padding:0.35rem 0.8rem;text-decoration:none"
    >Print / PDF</a
  >
</form>

{% macro sort_link(col, label) %} {% set next_dir = 'desc' if (sort == col and
dir == 'asc') else 'asc' %} {% set arrow = ' ↑' if (sort == col and dir ==
'asc') else (' ↓' if (sort == col and dir == 'desc') else '') %}
<a
  href="?status={{ active_status }}&type={{ active_type | urlenc }}&q={{ query | urlenc }}&has_contact={{ has_contact }}&sort={{ col }}&dir={{ next_dir }}&page=1"
  class="sort-link"
  >{{ label }}{{ arrow }}</a
>
{% endmacro %} {% if contacts %}
<table>
  <thead>
    <tr>
      <th>{{ sort_link('id', '#') }}</th>
      <th>{{ sort_link('name', 'Name') }}</th>
      <th>{{ sort_link('city', 'City') }}</th>
      <th>{{ sort_link('type', 'Type') }}</th>
      <th>{{ sort_link('status', 'Status') }}</th>
      <th>{{ sort_link('fit', 'Fit') }}</th>
      <th>{{ sort_link('last_contact', 'Last contact') }}</th>
      <th>Email</th>
      <th>Website</th>
      <th>Notes</th>
      <th></th>
    </tr>
  </thead>
  <tbody>
    {% for c in contacts %}
    <tr>
      <td class="muted small">{{ c.id }}</td>
      <td>
        <strong><a href="/contacts/{{ c.id }}">{{ c.name }}</a></strong>
      </td>
      <td>
        {{ c.city }}{% if c.country %}
        <span class="muted">{{ c.country }}</span>{% endif %}
      </td>
      <td class="muted">{{ c.type or '—' }}</td>
      <td><span class="badge badge-{{ c.status }}">{{ c.status }}</span></td>
      <td>
        {% if c.fit_score is not none %}{{ c.fit_score }}{% else %}<span
          class="muted"
          >—</span
        >{% endif %}
      </td>
      <td class="muted">
        {{ c.last_contact.strftime('%Y-%m-%d') if c.last_contact else '—' }}
      </td>
      <td class="muted small">{{ c.email or '—' }}</td>
      <td class="muted small">
        {% if c.website %}<a href="{{ c.website }}" target="_blank"
          >{{ c.website }}</a
        >{% else %}—{% endif %}
      </td>
      <td class="muted small notes-cell">
        <div class="notes-cell-inner">{{ c.notes or '—' }}</div>
      </td>
      <td>
        {% if c.flagged %}
        <span class="flag-dot" title="Flagged for review">●</span>
        <form
          method="post"
          action="/contacts/{{ c.id }}/delete"
          style="display:inline"
          onsubmit="return confirm('Delete {{ c.name }}?')"
        >
          <button class="btn-danger btn-tiny">del</button>
        </form>
        <form
          method="post"
          action="/contacts/{{ c.id }}/unflag"
          style="display:inline"
        >
          <button class="btn-tiny">keep</button>
        </form>
        {% endif %}
      </td>
    </tr>
    {% endfor %}
  </tbody>
</table>
{% else %}
<p class="empty">No contacts found.</p>
{% endif %} {% if total_pages > 1 %}
<div class="pagination">
  {% if page > 1 %}
  <a
    href="?status={{ active_status }}&type={{ active_type | urlenc }}&q={{ query | urlenc }}&has_contact={{ has_contact }}&sort={{ sort }}&dir={{ dir }}&page={{ page - 1 }}"
    class="btn-secondary"
    >← Prev</a
  >
  {% endif %}
  <span class="muted">Page {{ page }} of {{ total_pages }}</span>
  {% if page < total_pages %}
  <a
    href="?status={{ active_status }}&type={{ active_type | urlenc }}&q={{ query | urlenc }}&has_contact={{ has_contact }}&sort={{ sort }}&dir={{ dir }}&page={{ page + 1 }}"
    class="btn-secondary"
    >Next →</a
  >
  {% endif %}
</div>
{% endif %} {% endblock %}
```

---

## Step 5 — Create `gcrm/ui/templates/contact_detail.html`

Copy verbatim from art-crm:
`~/programming/art-crm/artcrm-supervisor/src/ui/templates/contact_detail.html`

No changes needed — fully generic.

---

## Step 6 — Create `gcrm/ui/templates/contact_brief.html`

Copy from art-crm:
`~/programming/art-crm/artcrm-supervisor/src/ui/templates/contact_brief.html`

Then change ONE thing in the interview reminder box:

- `artcrm-interview` → `engcrm-interview`
- The hint text: change "ArtCRM" references to "EngCRM" if any appear in static text

---

## Step 7 — Create `gcrm/ui/templates/contacts_print.html`

Copy verbatim from:
`~/programming/art-crm/artcrm-supervisor/src/ui/templates/contacts_print.html`

No changes needed.

---

## Step 8 — Create `STATUSES.md`

Create at the repo root:

```markdown
# Contact Statuses

## Pipeline Statuses (automated flow)

| Status      | Description                                                                            |
| ----------- | -------------------------------------------------------------------------------------- |
| `candidate` | Freshly discovered by the research agent. Not yet evaluated — no scoring, no outreach. |
| `cold`      | Scored by the scout agent as a good fit. Ready for first-contact outreach.             |
| `contacted` | First outreach has been sent. Waiting for a response.                                  |

## Positive Progression

| Status             | Description                                                                          |
| ------------------ | ------------------------------------------------------------------------------------ |
| `meeting`          | A meeting or discovery call has been arranged or confirmed.                          |
| `proposal`         | A proposal or quote has been sent. Awaiting decision.                                |
| `accepted`         | Contact has agreed to proceed with a project. Active client relationship.            |
| `networking_visit` | Responded positively but no immediate project. Flagged to stay in touch and revisit. |

## Inactive / Stalled

| Status    | Description                                                                                                     |
| --------- | --------------------------------------------------------------------------------------------------------------- |
| `dormant` | Was active at some point but has gone quiet. No interaction within the dormancy threshold (default: 12 months). |
| `on_hold` | Manually parked — timing not right, budget not available. Revisit later.                                        |

## Dead Ends

| Status           | Description                                                                                                                                                                                          |
| ---------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `dropped`        | Decided not to pursue after at least one contact attempt — wrong fit, no response after multiple tries, or business closed. Never set before first contact; use `cold` if no outreach has been made. |
| `rejected`       | Prospect explicitly declined.                                                                                                                                                                        |
| `do_not_contact` | Opted out or explicitly asked not to be contacted. Blocked from all outreach.                                                                                                                        |

## Data Quality

| Status      | Description                                                                                         |
| ----------- | --------------------------------------------------------------------------------------------------- |
| `bad_email` | Outreach email bounced or was undeliverable. Email address needs to be verified before re-outreach. |

---

## Flow
```

candidate → (scout scores) → cold → (outreach sent) → contacted
↓
meeting → proposal → accepted / networking_visit
↓
dormant / on_hold / dropped / do_not_contact

```

```

---

## Step 9 — Create the interview agent

Create a new package at `~/programming/eng-crm/engcrm-interview-agent/`.

### Directory structure

```
engcrm-interview-agent/
  pyproject.toml
  engcrm_interview_agent/
    __init__.py
    db.py
    interview.py
```

### `pyproject.toml`

```toml
[project]
name = "engcrm-interview-agent"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "psycopg2-binary>=2.9.9",
    "python-dotenv>=1.0.0",
]

[project.scripts]
engcrm-interview = "engcrm_interview_agent.interview:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["engcrm_interview_agent"]
```

### `engcrm_interview_agent/__init__.py`

Empty file.

### `engcrm_interview_agent/db.py`

```python
import os
import psycopg2
import psycopg2.extras
from contextlib import contextmanager
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]


def get_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)


@contextmanager
def db():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
```

### `engcrm_interview_agent/interview.py`

```python
"""
EngCRM — Post-Meeting Debrief Interview

Interviews you after a face-to-face meeting or discovery call and saves answers
directly to the database.

Usage:
    uv run engcrm-interview
    # or:
    uv run python -m engcrm_interview_agent.interview

Voice input tip (Ubuntu/Wayland):
    Install nerd-dictation: https://github.com/ideasman42/nerd-dictation
    Works system-wide — speak and it types into any terminal.
"""
import sys
from datetime import date

from engcrm_interview_agent.db import db

# Import vertical config for customisable options.
# Falls back to eng-specific defaults if vertical.py is not on the path.
try:
    import sys as _sys
    import os as _os
    _sys.path.insert(0, _os.path.expanduser("~/programming/eng-crm"))
    from gcrm.vertical import INTERVIEW_APP_NAME, INTERVIEW_MATERIALS_OPTIONS
except (ImportError, AttributeError):
    INTERVIEW_APP_NAME = "EngCRM"
    INTERVIEW_MATERIALS_OPTIONS = [
        "business card",
        "one-pager",
        "demo link",
        "proposal",
        "case study",
        "Förderung info sheet",
        "nothing",
    ]


# ── UI helpers ────────────────────────────────────────────────────────────────

def hr():
    print("\n" + "─" * 50)


def ask(prompt, default=None):
    suffix = f" [{default}]" if default else " (Enter to skip)"
    val = input(f"  {prompt}{suffix}: ").strip()
    return val if val else default


def menu(prompt, options, allow_skip=True):
    print(f"\n  {prompt}")
    for i, opt in enumerate(options, 1):
        print(f"    {i}. {opt}")
    if allow_skip:
        print("    0. skip")
    while True:
        raw = input("  Choice: ").strip()
        if allow_skip and raw in ("", "0"):
            return None
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(options):
                return options[idx]
        except ValueError:
            pass
        print("  Invalid — try again.")


def multi_menu(prompt, options):
    print(f"\n  {prompt}")
    for i, opt in enumerate(options, 1):
        print(f"    {i}. {opt}")
    print("    0. skip / none")
    while True:
        raw = input("  Choices (e.g. 1,3): ").strip()
        if not raw or raw == "0":
            return []
        try:
            idxs = [int(x.strip()) - 1 for x in raw.split(",")]
            if all(0 <= i < len(options) for i in idxs):
                return [options[i] for i in idxs]
        except ValueError:
            pass
        print("  Invalid — try again.")


# ── database ──────────────────────────────────────────────────────────────────

def search_contacts(query: str) -> list[dict]:
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, name, city, country, status, type, first_impression
            FROM contacts
            WHERE deleted_at IS NULL
              AND (lower(name) LIKE %s OR lower(city) LIKE %s)
            ORDER BY lower(name)
            LIMIT 15
            """,
            (f"%{query.lower()}%", f"%{query.lower()}%"),
        )
        return [dict(r) for r in cur.fetchall()]


def save_updates(contact_id: int, updates: dict):
    if not updates:
        return
    fields = ", ".join(f"{k} = %s" for k in updates)
    values = list(updates.values()) + [contact_id]
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            f"UPDATE contacts SET {fields}, updated_at = NOW() WHERE id = %s",
            values,
        )


def append_notes(contact_id: int, new_text: str):
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT notes FROM contacts WHERE id = %s", (contact_id,))
        row = cur.fetchone()
        existing = (row["notes"] or "").strip()
        today = date.today().isoformat()
        combined = f"{existing}\n\n[{today}] {new_text}".strip() if existing else f"[{today}] {new_text}"
        cur.execute(
            "UPDATE contacts SET notes = %s, updated_at = NOW() WHERE id = %s",
            (combined, contact_id),
        )


# ── contact picker ────────────────────────────────────────────────────────────

def pick_contact() -> dict | None:
    while True:
        query = input("\n  Search company name or city (or Enter to finish): ").strip()
        if not query:
            return None

        results = search_contacts(query)
        if not results:
            print("  No matches found. Try again.")
            continue

        print(f"\n  Found {len(results)} match(es):")
        for i, c in enumerate(results, 1):
            loc = f"{c['city']}, {c['country']}" if c.get("country") else c.get("city", "")
            print(f"    {i}. {c['name']}  [{loc}]  {c['status']}")
        print("    0. search again")

        raw = input("  Select: ").strip()
        if raw == "0" or not raw:
            continue
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(results):
                return results[idx]
        except ValueError:
            pass
        print("  Invalid — try again.")


# ── interview ─────────────────────────────────────────────────────────────────

VALID_STATUSES = [
    "candidate", "cold", "contacted", "networking_visit",
    "meeting", "proposal", "accepted", "on_hold", "dropped", "do_not_contact",
]


def interview_contact(contact: dict) -> None:
    hr()
    loc = contact.get("city", "")
    print(f"\n  Company : {contact['name']}  {loc}  [{contact['status']}]")
    if contact.get("first_impression"):
        print(f"  First impression on record: {contact['first_impression']}")

    updates = {}
    today_str = date.today().isoformat()

    # Date of meeting
    visited = ask("Date of meeting", default=today_str)
    if visited:
        updates["last_visited_at"] = visited

    # Status update
    current = contact.get("status", "")
    new_status = menu(f"Update status? (current: {current})", VALID_STATUSES)
    if new_status:
        updates["status"] = new_status

    # Who did you meet
    dm = ask("Who did you meet? (name / role / title)")
    if dm:
        updates["decision_maker"] = dm

    # Impression / tone
    impression = menu("How did the meeting go?", ["warm", "neutral", "cold", "skeptical"])
    if impression:
        updates["last_impression"] = impression
        if not contact.get("first_impression"):
            updates["first_impression"] = impression

    # Materials / collateral shared
    materials = multi_menu("What did you share or leave?", INTERVIEW_MATERIALS_OPTIONS)
    if materials:
        updates["materials_left"] = ", ".join(materials)

    # Follow-up commitments
    followup = ask("What did you commit to? (e.g. 'send proposal by Friday', 'demo next week')")
    if followup:
        updates["followup_promised"] = followup

    # Preferred contact method going forward
    pref = menu(
        "Best way to reach them going forward?",
        ["email", "phone", "LinkedIn", "in person", "via assistant"],
    )
    if pref:
        updates["preferred_contact_method"] = pref

    # Contact details gathered
    got_email = ask("Did you get a direct email address?")
    if got_email:
        updates["email"] = got_email

    got_phone = ask("Did you get a direct phone number?")
    if got_phone:
        updates["phone"] = got_phone

    # Office / logistics notes
    access = ask("Office / logistics notes? (location, parking, reception process…)")
    if access:
        updates["access_notes"] = access

    # Company / team observations
    space = ask("Company notes? (team size, tech stack visible, culture vibe…)")
    if space:
        updates["space_notes"] = space

    # Budget / commercial signals
    price = ask("Budget / commercial signals? (mentioned Förderung, price sensitivity, decision timeline…)")
    if price:
        updates["price_sensitivity"] = price

    # Best time to follow up
    best_time = ask("Best time / channel for follow-up?")
    if best_time:
        updates["best_visit_time"] = best_time

    # Free notes
    free_notes = ask("Anything else to note?")

    # Persist
    save_updates(contact["id"], updates)
    if free_notes:
        append_notes(contact["id"], free_notes)

    saved_fields = list(updates.keys()) + (["notes"] if free_notes else [])
    print(f"\n  Saved: {', '.join(saved_fields)}")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"\n  {INTERVIEW_APP_NAME} — Post-Meeting Debrief")
    print("  Search for each company you met today. Empty search = done.\n")

    count = 0
    while True:
        contact = pick_contact()
        if contact is None:
            break
        interview_contact(contact)
        count += 1

    hr()
    if count == 0:
        print("\n  No contacts logged. Goodbye.\n")
    else:
        print(f"\n  Done — {count} contact(s) updated. Goodbye.\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  Interrupted. Any saves already made are kept.\n")
        sys.exit(0)
```

### Install the agent

From `~/programming/eng-crm/engcrm-interview-agent/`:

```bash
uv pip install -e .
# or:
pip install -e .
```

---

## Step 10 — Verify

```bash
# Test the web app starts
cd ~/programming/eng-crm
uv run uvicorn gcrm.api.main:app --reload

# Check:
# - contact list loads with type + has_contact filters
# - click a contact name → detail page
# - click "Pre-visit brief" → brief page with engcrm-interview command shown
# - /contacts/print → print view

# Test the interview agent
engcrm-interview
```

---

## Notes

- Do NOT change any existing keys in `vertical.py` — only add the two new ones from Step 2
- Do NOT change any agent logic, supervisor scripts, or MCP server
- The `.env` stays as-is
- The interview questions are tuned for B2B software/AI consulting — "venue" language replaced with "company/meeting" language throughout
