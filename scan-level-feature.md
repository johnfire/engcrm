# Feature: Emails Sent Per Level on Research Page

## What It Does

Adds 5 "Sent L1–L5" columns to the research page table. Each column shows how many contacts in that city have been emailed at that scan level. This lets you see at a glance how far outreach has progressed across each research level per city.

## The Problem It Solves

Contacts had no record of which scan level found them. Without that, you can't count "emails sent at level 2 in Augsburg" — you don't know which contacts came from level 2.

## Changes Made

### 1. Database Migration — `src/db/migrations/006_contact_scan_level.sql`

Adds a `scan_level int` column to the `contacts` table and backfills existing contacts by mapping their `type` to a level:

```sql
ALTER TABLE contacts ADD COLUMN IF NOT EXISTS scan_level int;

UPDATE contacts SET scan_level = CASE
    WHEN type IN ('gallery', 'cafe', 'interior_designer', 'coworking') THEN 1
    WHEN type IN ('gift_shop', 'wellness', 'concept_store')            THEN 2
    WHEN type IN ('restaurant')                                         THEN 3
    WHEN type IN ('corporate_office')                                   THEN 4
    WHEN type IN ('hotel')                                              THEN 5
    ELSE NULL
END
WHERE scan_level IS NULL;
```

After the initial migration, a second pass was run to catch additional unmapped types:

```sql
UPDATE contacts SET scan_level = 1
WHERE scan_level IS NULL AND (
    type ILIKE '%gallery%' OR type ILIKE '%museum%'
    OR type ILIKE '%cafe%' OR type ILIKE '%art collective%'
);

UPDATE contacts SET scan_level = 2
WHERE scan_level IS NULL AND type ILIKE '%gift shop%';

UPDATE contacts SET scan_level = 4
WHERE scan_level IS NULL AND type = 'office';
```

Contacts with ambiguous types (`other`, `online_platform`, freeform strings) are left as NULL — they simply don't appear in the sent counts.

---

### 2. `src/tools/db.py` — `save_contact()`

Added an optional `scan_level` parameter so all contacts created by the research agent going forward are tagged with their level at insert time.

```python
def save_contact(
    name: str,
    city: str,
    *,
    ...
    scan_level: int | None = None,
) -> int:
```

The INSERT statement was updated to include `scan_level`:

```python
INSERT INTO contacts (name, city, country, type, website, email, phone, notes, status, scan_level)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'candidate', %s)
```

---

### 3. `src/tools/db.py` — `get_all_city_scan_status()`

Extended the query to join in a subquery that counts contacted contacts grouped by city and scan level. "Emailed" means status is one of: `contacted`, `meeting`, `proposal`, `accepted`.

```sql
LEFT JOIN (
    SELECT lower(city) AS city_lower, scan_level, COUNT(*) AS cnt
    FROM contacts
    WHERE status IN ('contacted', 'meeting', 'proposal', 'accepted')
      AND scan_level IS NOT NULL
    GROUP BY lower(city), scan_level
) emailed ON lower(ci.city) = emailed.city_lower
```

The result includes a new `emailed_by_level` JSON object, e.g. `{"1": 2, "3": 1}`.

---

### 4. Research Agent — `graph.py` (`save_contacts` node)

Passes `state["level"]` to `save_contact` so every contact saved by the research agent is tagged with the level that found it:

```python
contact_id = save_contact(
    ...
    scan_level=state.get("level"),
)
```

---

### 5. `src/api/routers/research.py`

Converts the `emailed_by_level` dict into a 5-element list (one entry per level, defaulting to 0) for easy template iteration:

```python
emailed = c.get("emailed_by_level") or {}
c["emailed"] = [emailed.get(str(lvl), 0) for lvl in range(1, 6)]
```

---

### 6. `src/ui/templates/research.html`

Added 5 new header columns and 5 new data cells per row:

```html
<th title="Emails sent at level 1">Sent L1</th>
...
<th title="Emails sent at level 5">Sent L5</th>
```

```html
{% for count in c.emailed %}
<td class="center {% if count %}text-success{% else %}muted{% endif %}">
  {{ count if count else '—' }}
</td>
{% endfor %}
```

## Notes for general-crm

- The type-to-level mapping in the migration should match whatever scan levels are defined in `vertical.py`. Update the CASE statement accordingly.
- The `status` values treated as "emailed" (`contacted`, `meeting`, `proposal`, `accepted`) are the same pipeline stages — no changes needed there.
- The agent package that needs updating is `gcrm-research-agent/graph.py` — same one-line change to pass `scan_level` to `save_contact`.
