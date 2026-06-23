# Business-Card Capture — MVP Build Plan

**Goal:** in the field, snap a photo of a business card → it becomes a reviewed,
deduped lead in engcrm, with enrichment kicked off on confirm.

**Framing:** the camera is a new *front-door* to the funnel that already exists
(enrichment → research → outreach → approval). The photo isn't the feature; it's
the lowest-friction way to drop a lead into the top of that funnel from the street.

## Locked decisions
- **Card first** (storefront/GPS mode is a later v2).
- **Image storage:** on the VPS (Docker volume), not S3.
- **Enrichment:** triggered **on confirm**, not on capture.
- **Vision model:** Claude **Haiku 4.5** via the existing `ANTHROPIC_API_KEY` +
  `get_llm("claude-haiku")`. No subscription, no new key. ~¼¢/card.

## End-to-end flow
```
[mobile] snap → downscale → POST /api/cards (multipart)
   → [server] store image on volume → Claude Haiku vision → structured JSON
   → dedup check (email / domain / name+city / phone)
   → return {capture_id, fields, dup_suggestion, confidence}
[mobile] confirm/edit screen (+ "possible duplicate" banner)
   → POST /api/cards/{id}/confirm {edited fields, link_to_contact_id?}
   → [server] save_contact() (or link) → enrich_one(contact_id) in background
   → push "Lead {name} enriched & ready" when done
```
Offline: capture is queued locally and uploads when signal returns. A card is
never lost because the network or the model hiccuped (anti-fragility).

---

## 1. Data model — migration `023_card_captures.sql`

A **staging table** decouples capture (offline-tolerant, may fail extraction)
from the clean `contacts` row, and preserves provenance for GDPR.

```sql
CREATE TABLE card_captures (
    id                  SERIAL PRIMARY KEY,
    captured_by         INTEGER REFERENCES users(id),
    captured_at         TIMESTAMPTZ DEFAULT NOW(),
    image_path          TEXT,                          -- relative path under CARD_IMAGE_DIR
    gps_lat             DOUBLE PRECISION,              -- nullable; for v2 storefront mode
    gps_lng             DOUBLE PRECISION,
    status              VARCHAR(30) DEFAULT 'pending_review', -- pending_review|confirmed|discarded
    extraction_status   VARCHAR(20) DEFAULT 'pending', -- pending|done|failed
    extracted           JSONB,                         -- raw structured fields from Claude
    extraction_model    VARCHAR(60),
    extraction_cost_usd NUMERIC(10,5),
    confidence          SMALLINT,                      -- 0-100, from the model
    dup_contact_id      INTEGER REFERENCES contacts(id), -- suggested duplicate (nullable)
    contact_id          INTEGER REFERENCES contacts(id), -- set on promote
    error               TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_card_captures_status ON card_captures(status);

-- tag where a contact came from (analytics + GDPR provenance)
ALTER TABLE contacts ADD COLUMN IF NOT EXISTS source VARCHAR(40);
```

### Card → contact mapping (uses existing field-sales columns)
| card field        | contacts column                    |
|-------------------|------------------------------------|
| company           | `name` (the business)              |
| person + title    | `decision_maker` (`"Anna Roth, CTO"`) |
| email             | `email`  (direct line — high value)|
| phone / mobile    | `phone`                            |
| website           | `website`                          |
| address           | `address`                          |
| city / country    | `city` / `country`                 |
| industry (inferred)| `type`                            |
| —                 | `source = 'card_capture'`, `status = 'candidate'` |

If there's no company (freelancer), `name` = person. The confirm screen lets the
user flip this. `status='candidate'` is what plugs the lead into the existing
enrichment queue (`get_contacts_needing_enrichment`).

---

## 2. Backend

### 2a. Image storage (VPS volume)
- New env: `CARD_IMAGE_DIR=/data/card-images`.
- `docker-compose.yml`: add a named volume to the `app` service:
  ```yaml
  volumes:
    - card-images:/data/card-images
  # and under top-level volumes:
  card-images:
  ```
- Images are **personal data** → never serve via public `/static`. Serve through
  an authenticated endpoint `GET /api/cards/{id}/image` (require_jwt).
- Filename: `{capture_id}.jpg`. Mobile downscales to ≤1280px JPEG before upload,
  so files are ~100–300 KB and vision tokens stay low.

### 2b. Vision extraction — `gcrm/tools/cards.py`
```python
def extract_card_fields(image_bytes: bytes) -> dict:
    """Claude Haiku 4.5 vision → strict JSON dict (see prompt in §5).
    Cost is auto-tracked via the existing _get_cost_callback() / run_costs."""
```
- Uses `get_llm("claude-haiku")` (already wired) with a multimodal message:
  a base64 image block + the extraction prompt. `temperature=0`.
- Returns the parsed JSON (`is_card`, `confidence`, fields…). On non-card /
  unreadable, `is_card=false` → surface "couldn't read it, retake".

### 2c. Dedup — `gcrm/tools/cards.py: find_possible_duplicate(fields) -> dict|None`
Reuse + extend existing logic, in priority order:
1. exact email (`match_contact_by_email` already does email + corporate-domain),
2. normalized phone match,
3. `lower(name)=company AND lower(city)=city`.
Returns the matched contact (for the "possible duplicate" banner) or None.
`save_contact()` still double-guards on insert (returns 0 on dup).

### 2d. API router — `gcrm/api/routers/api_cards.py` (mirror `api_contacts.py`, `require_jwt`)
| method | path | purpose |
|---|---|---|
| `POST` | `/api/cards` | multipart `image` (+ optional `gps_lat/lng`). Store → extract → dedup → return `{capture_id, fields, dup_suggestion, confidence}`. **Sync** for MVP (~2–4 s). |
| `GET`  | `/api/cards?status=pending_review` | list pending captures (enables batch / conference review) |
| `GET`  | `/api/cards/{id}/image` | auth'd image fetch |
| `POST` | `/api/cards/{id}/confirm` | body = edited fields + optional `link_to_contact_id`. Promote → `contact_id`. Kick enrichment. |
| `POST` | `/api/cards/{id}/discard` | mark discarded, delete image |

Mount in `gcrm/api/main.py` next to the other `api_*` routers.

### 2e. Enrich-on-confirm — `enrich_one(contact_id)`
- On confirm: `save_contact(...)` (+ `update_contact_details` for `decision_maker`,
  `source`) → then enrich **that one contact** in a FastAPI `BackgroundTask`.
- Implementation: reuse the enrichment agent factory exactly as
  `gcrm/supervisor/run_enrichment.py` builds it, but scoped to a single
  `contact_id`. On completion → `send_push_to_all(title="Lead ready",
  body=f"{name} enriched", data={"screen":"contacts"})`.
- API returns immediately with `contact_id`; enrichment runs async so the UI
  isn't blocked. (Fallback if we don't want a live run: just leave it
  `status='candidate'` and the scheduled supervisor picks it up.)

---

## 3. Mobile (`engcrm-mobile`)

New deps (native → next CI android build picks them up automatically — that
pipeline is now proven): `expo-camera` (or `expo-image-picker`),
`expo-image-manipulator` (downscale), `expo-file-system` + the existing
async-storage for the offline queue.

- **`app/(drawer)/capture.tsx`** — camera screen, prominent entry (FAB or first
  drawer item). Capture → `expo-image-manipulator` resize ≤1280px / JPEG q0.7 →
  `services/api.ts: captureCard(uri, gps?)` → on success, navigate to confirm.
- **Confirm screen** — extracted fields in editable inputs; a yellow
  **"Possible duplicate: {name}"** banner with **[Open existing]** /
  **[Create new]**; buttons **[Save lead] [Retake] [Discard]**.
- **Offline queue** — if `captureCard` fails (no signal), persist
  `{localImageUri, gps, ts}` to a queue (file + async-storage); a small badge
  shows pending count; flush on reconnect / app foreground. Review extracted
  cards later from the pending list (batch / conference mode falls out of this).
- **`services/api.ts`** — add `captureCard()`, `confirmCard()`, `discardCard()`,
  `listPendingCards()`. Reuse the existing JWT `authedFetch`.

---

## 4. GDPR / retention (DE — real, not theatre)
- A card **handed to you** is a softer lawful basis for B2B contact than scraped
  data — this is your *cleanest* lead source. Still:
- `captured_by` + `captured_at` + `source='card_capture'` = provenance.
  `ensure_consent_log()` already fires inside `save_contact()`.
- **Image retention:** default — delete the image file on `confirm` (we keep the
  extracted text, which is the minimum needed). Discarded captures: delete image
  immediately. Configurable `CARD_IMAGE_RETENTION_DAYS` if you'd rather keep them.
- **No auto-send.** The human approval gate (`queue_for_approval` → mobile
  approvals) stays — capture never triggers an email by itself.

---

## 5. Extraction prompt (`gcrm/prompts/cards.py`)
```
SYSTEM:
You extract structured data from a photo of a SINGLE business card.
Return ONLY a JSON object matching the schema. Extract only what is visibly
printed on the card — never guess, infer, or invent. Use null for anything not
present. Normalize phone numbers to international +CC format when the country is
clear. Detect the card's primary language. If the image is not a business card
or is unreadable, set is_card=false and say why in `note`.

SCHEMA:
{
  "is_card": bool,
  "confidence": 0-100,
  "company":  string|null,
  "name":     string|null,   // person's full name
  "title":    string|null,   // job title / role
  "email":    string|null,
  "phone":    string|null,   // landline / main
  "mobile":   string|null,
  "website":  string|null,
  "address":  string|null,
  "city":     string|null,
  "country":  string|null,   // ISO-3166 alpha-2
  "industry": string|null,   // inferred B2B category, e.g. "Zahnarzt", "Steuerberater"
  "language": string|null,   // ISO-639-1
  "note":     string|null    // handwriting, second person, ambiguity, etc.
}
```
User message = the image block. Model `claude-haiku-4-5-20251001`, temp 0.

---

## 6. Build phases
1. **Backend** — migration 023; `cards.py` (extract + dedup); `api_cards.py`;
   `enrich_one`; compose volume + env; tests (extraction parsing with a fixture
   image, dedup hits, confirm→contact, discard cleanup).
2. **Mobile** — deps; capture screen; confirm/dedup screen; api client; offline
   queue. Push to `engcrm-mobile/**` → CI builds + submits to Play internal.
3. **(Optional, later)** desktop web review page for the pending queue; v2
   storefront + GPS mode.

## 7. Open decisions (need your call before I build)
1. **Sync vs async extraction** on `POST /api/cards`. MVP = sync (user waits
   ~2–4 s, simplest). Async (return id, push when extracted) only if you want
   instant shutter-to-next-card at conferences. → *recommend sync for MVP.*
2. **Image retention** — delete on confirm (privacy-min) vs keep N days (lets you
   re-extract / audit). → *recommend delete-on-confirm, env-configurable.*
3. **Lead status** — reuse `'candidate'` (flows into existing enrichment) vs add a
   distinct `'lead'`/`'captured'` status for reporting. → *recommend reuse
   `'candidate'` + the new `source` column does the reporting.*
4. **Enrichment on confirm** — live background run with push (snappy, costs a
   DeepSeek enrichment immediately) vs drop in queue for the scheduled run. →
   *recommend live background run, since you asked for "on confirm".*

## 8. Rough effort
Backend ~1 focused session; mobile ~1 session; then a real-card test pass.
Marginal running cost: ~¼¢/card vision + the normal DeepSeek enrichment per lead.
