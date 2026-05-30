# Add Inbox, Marketing & Drafts to eng-crm UI

Port the three nav sections from artcrm-supervisor so the eng-crm supervisor UI matches it.

---

## Overview of changes

| Area          | Files                                                                      |
| ------------- | -------------------------------------------------------------------------- |
| Nav           | `gcrm/ui/templates/base.html`                                              |
| Templates     | `inbox.html`, `marketing.html`, `drafts.html`, `partials/drafts_list.html` |
| Routers       | `gcrm/api/routers/inbox.py`, `marketing.py`, `drafts.py`                   |
| App wiring    | `gcrm/api/main.py`                                                         |
| DB migrations | 2 new migration files                                                      |

---

## 1. DB migrations

### Migration: `012_inbox_classification.sql`

The eng-crm `inbox_messages` table is missing the classification columns the Inbox screen relies on.

```sql
ALTER TABLE inbox_messages
  ADD COLUMN IF NOT EXISTS classification          VARCHAR(60),
  ADD COLUMN IF NOT EXISTS classification_reasoning TEXT,
  ADD COLUMN IF NOT EXISTS visit_when_nearby        BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_inbox_classification
  ON inbox_messages (classification)
  WHERE processed = TRUE;
```

### Migration: `013_approval_queue_on_hold.sql`

The Drafts screen shows `approval_queue` rows with `status = 'on_hold'`. The current status enum comment lists `pending | approved | rejected | edited` — add `on_hold` and `approved_unsent`.

```sql
-- No constraint to alter, status is VARCHAR(20). Just document the new values
-- and add the reviewer_note + final_body columns if not already present
-- (they exist in 001_agent_tables.sql so this is a no-op guard):
ALTER TABLE approval_queue
  ADD COLUMN IF NOT EXISTS final_body TEXT;

COMMENT ON COLUMN approval_queue.status IS
  'pending | approved | approved_unsent | rejected | edited | edited_unsent | on_hold';
```

---

## 2. Update `base.html`

File: `gcrm/ui/templates/base.html`

Add three nav links after the existing Research link:

```html
    <a href="/research/" {% if request.url.path.startswith('/research') %}class="active"{% endif %}>
      Research
    </a>
    <a href="/inbox/" {% if request.url.path.startswith('/inbox') %}class="active"{% endif %}>
      Inbox
    </a>
    <a href="/marketing/" {% if request.url.path.startswith('/marketing') %}class="active"{% endif %}>
      Marketing
    </a>
    <a href="/drafts/" {% if request.url.path.startswith('/drafts') %}class="active"{% endif %}>
      Drafts
    </a>
```

Also update the brand name if desired (`AI-CRM Leads` → whatever the eng-crm supervisor is called).

---

## 3. New templates

### `gcrm/ui/templates/inbox.html`

Copy verbatim from `artcrm-supervisor/src/ui/templates/inbox.html`, with these substitutions:

- `{% block title %}Inbox Replies — ArtCRM Supervisor{% endblock %}` → `{% block title %}Inbox Replies — AI-CRM Leads{% endblock %}`
- All other content is identical; the template uses no artcrm-specific variables beyond those provided by the router.

### `gcrm/ui/templates/drafts.html`

```html
{% extends "base.html" %} {% block title %}Held Drafts — AI-CRM Leads{% endblock
%} {% block content %}
<div class="page-header">
  <h1>Held Drafts</h1>
  <span class="muted"
    >{{ drafts|length }} email{{ 's' if drafts|length != 1 else '' }} on
    hold</span
  >
</div>

<div id="drafts-list">{% include "partials/drafts_list.html" %}</div>
{% endblock %}
```

### `gcrm/ui/templates/partials/drafts_list.html`

Copy verbatim from `artcrm-supervisor/src/ui/templates/partials/drafts_list.html`.

No substitutions needed — all paths (`/drafts/`, `/contacts/`) are identical.

### `gcrm/ui/templates/marketing.html`

The artcrm marketing page depends on strategy docs and Open Brain integration that eng-crm doesn't have yet. Use a minimal stub that can be extended later:

```html
{% extends "base.html" %} {% block title %}Marketing — AI-CRM Leads{% endblock
%} {% block content %}
<div class="page-header">
  <h1>Marketing</h1>
  <span class="muted">Weekly strategy digest</span>
</div>

{% if digest %}
<section style="margin-bottom: 2rem;">
  <h2
    style="font-size:1rem; text-transform:uppercase; letter-spacing:.05em; color:var(--muted); margin-bottom:.75rem;"
  >
    Digest — {{ digest.week_date }}
  </h2>
  <div class="digest-content" style="max-width:72ch; line-height:1.7;">
    {{ digest.content_html | safe }}
  </div>
</section>
{% else %}
<section style="margin-bottom: 2rem;">
  <p class="muted">No digest yet.</p>
</section>
{% endif %} {% if strategies %}
<section style="margin-bottom: 2rem;">
  <h2
    style="font-size:1rem; text-transform:uppercase; letter-spacing:.05em; color:var(--muted); margin-bottom:.75rem;"
  >
    Strategies
  </h2>
  <table>
    <thead>
      <tr>
        <th>Name</th>
        <th>Status</th>
        <th>Priority</th>
        <th>Last reviewed</th>
      </tr>
    </thead>
    <tbody>
      {% for s in strategies %}
      <tr>
        <td><strong>{{ s.name }}</strong></td>
        <td>
          <span
            class="badge {% if s.status == 'active' %}badge-green{% elif s.status == 'on_hold' %}badge-yellow{% else %}badge-grey{% endif %}"
          >
            {{ s.status }}
          </span>
        </td>
        <td class="center">{{ s.priority }}</td>
        <td class="muted small">
          {{ s.last_reviewed_at[:10] if s.last_reviewed_at else '—' }}
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</section>
{% endif %} {% endblock %}
```

> To get the full marketing page (digests, strategy editor, observations) later, add the `marketing_strategies` and `marketing_digests` tables and copy the artcrm `marketing_db` tools module.

---

## 4. New router files

### `gcrm/api/routers/inbox.py`

Copy from `artcrm-supervisor/src/api/routers/inbox.py` with these substitutions:

```python
# Change import:
from src.db.connection import db  →  from gcrm.db.connection import db

# Change templates path:
Path(__file__).parent.parent.parent / "ui" / "templates"
# (already correct for gcrm layout — verify depth matches approval.py)
```

The SQL query is identical; the `inbox_messages` table and `contacts` table exist in eng-crm with the same column names (after migration 012).

### `gcrm/api/routers/drafts.py`

Copy from `artcrm-supervisor/src/api/routers/drafts.py` with substitutions:

```python
# Imports:
from src.db.connection import db       →  from gcrm.db.connection import db
from src.tools.email import send_email →  from gcrm.tools.email import send_email
from src.tools.db import log_interaction → from gcrm.tools.db import log_interaction
```

The SQL references `approval_queue.status = 'on_hold'` and `contacts` columns that all exist in eng-crm (after migration 013).

### `gcrm/api/routers/marketing.py`

Minimal stub (no strategy docs or Open Brain yet):

```python
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent.parent / "ui" / "templates"))


@router.get("/marketing/", response_class=HTMLResponse)
def marketing_page(request: Request):
    return templates.TemplateResponse("marketing.html", {
        "request": request,
        "strategies": [],
        "digest": None,
        "archive": [],
    })
```

---

## 5. Wire up routers in `main.py`

File: `gcrm/api/main.py`

```python
# Add to imports:
from gcrm.api.routers import approval, activity, contacts, people, research, inbox, marketing, drafts

# Add after existing includes:
app.include_router(inbox.router)
app.include_router(marketing.router)
app.include_router(drafts.router)
```

---

## 6. Checklist

- [ ] Run migration `012_inbox_classification.sql`
- [ ] Run migration `013_approval_queue_on_hold.sql`
- [ ] Update `base.html` — add 3 nav links
- [ ] Create `templates/inbox.html`
- [ ] Create `templates/drafts.html`
- [ ] Create `templates/partials/drafts_list.html`
- [ ] Create `templates/marketing.html`
- [ ] Create `gcrm/api/routers/inbox.py`
- [ ] Create `gcrm/api/routers/drafts.py`
- [ ] Create `gcrm/api/routers/marketing.py`
- [ ] Update `gcrm/api/main.py`
- [ ] Restart dev server and verify all three nav items load without 500s
