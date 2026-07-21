# Feature plan: Scan a business sign → auto-research the business

**Status:** ready to implement · **Author:** planning session 2026-07-21 · **Target implementer:** coding agent
**Repo:** `engcrm` (`/home/chris/ppp2/engcrm`)

This document is self-contained — you do not need the planning conversation. It gives the goal,
the decisions already made, the exact code to reuse (with `file:line`), a phased build with
per-phase acceptance criteria, and the deploy path. Follow `.claude` / global coding standards
(tests required, ≤~60-line functions, isolate failure domains, audit-log user/AI actions,
clarity over cleverness). Work on `main`; do not create branches unless asked.

---

## 1. Goal

Add a mobile flow: **photograph a business storefront sign → the app reads the business name →
a background agent researches that one business on the web (what it does, key people, email,
phone, website) → the result lands in the CRM as a contact with linked people → a push
notification says it's ready.**

This is distinct from the existing **city-wide `research` pipeline** (`gcrm/supervisor/run_research.py`,
mission-driven, finds *many* venues in a city). This feature researches **one** business
identified from a sign photo + GPS.

## 2. Decisions already made (do not re-litigate)

| Decision | Choice |
| --- | --- |
| Research timing | **Background job + push notification** (mirror card-enrichment flow), not a blocking on-screen wait. |
| What the result becomes | **A CRM contact** (the business) **+ linked People** rows for key people found. Flows into the normal pipeline. |
| Web-research backend | **Google Places API (New) + web search.** Places nails the business from name+GPS; web search finds people/email. |
| Start screen | Already lands on Contacts; **additionally reorder the drawer so Contacts is first** and add the Scan-Sign entry near it. |

## 3. Deployment reality (context — mostly informational)

- **Backend** (`gcrm/`, FastAPI + Postgres): Dockerized (`Dockerfile` → `ghcr.io/johnfire/engcrm:latest`),
  runs on a **VPS behind Apache** at `https://engcrm.christopherrehm.de`. `docker-compose.yml` runs
  app + Postgres 16 + daily backups. Card/sign images persist on a VPS volume (`card-images:/data/card-images`).
- **Backend deploy is automatic:** push to `main` touching `gcrm/**` → `.github/workflows/backend.yml`
  runs tests → builds/pushes GHCR image → SSHes into the VPS to **pull + migrate + restart**. So a
  migration checked into `gcrm/db/migrations/` is applied on deploy — order your PRs so the migration
  lands before code that reads the new column.
- **Mobile** (`engcrm-mobile/`, Expo/React Native, pkg `de.christopherrehm.engcrm`): built as a signed
  Android AAB by a **self-hosted GitHub runner on Chris's laptop** (`.github/workflows/android.yml`,
  `runs-on: [self-hosted, android]`), optionally submitted to Play internal. **The laptop must be on**
  or the mobile build job queues. Not EAS cloud.
- **`GOOGLE_MAPS_API_KEY` already exists and works** — set in the local `.env` **and** verified
  present in the VPS `.env` (`/opt/engcrm/.env`, checked via SSH 2026-07-21), wired through
  `gcrm/config.py:24`, and already in production use by the city research pipeline's
  `google_maps_search`. So Places search is live; **no provisioning needed.** Only loose end: it is
  **not** documented in `.env.example` — add a placeholder line (no value). Still build
  `resolve_business` to **degrade to web-search-only** when the key is empty (`google_maps_search`
  returns `[]`) as a defensive default.
- **Bright Data Web Unlocker** is available: `BRIGHTDATA_API_TOKEN` is set in `.env` and the scraper
  layer "replaces plain httpx scraper." Prefer the existing Bright-Data-backed page fetch (whatever
  `fetch_page`/enrichment already uses) over raw httpx for the research step — better success rate on
  business sites that block plain scrapers.

## 4. Reuse map — the photo→vision→enrich→notify pipeline already exists for **cards**

Build the sign flow by paralleling the card flow, not from scratch.

| Concern | Reuse (exact location) | Notes |
| --- | --- | --- |
| Camera→resize→multipart upload | `engcrm-mobile/app/(drawer)/capture.tsx` | Fork it. `expo-location` is already a dep; attach GPS. |
| Upload API client | `captureCard()` in `engcrm-mobile/services/api.ts:167` | Already supports optional `gps: {lat,lng}`. Add a sibling `captureSign()`. |
| Store image + run vision | `POST /api/cards` in `gcrm/api/routers/api_cards.py:37` | Parallel `api_signs.py`. |
| Vision extraction | `cards.extract_card_fields()` `gcrm/tools/cards.py:43`; prompt `gcrm/prompts/cards.py` | New **sign prompt** (§6). Same Claude-vision call shape. |
| Save image to volume | `cards.save_card_image()` `gcrm/tools/cards.py:75` (+ `read_/delete_`) | Reuse as-is (same volume). |
| Duplicate detection | `cards.find_possible_duplicate()` `gcrm/tools/cards.py:111` | Reuse for the business name. |
| Confirm screen | `engcrm-mobile/app/(drawer)/card-confirm.tsx` | Slim variant: confirm/correct business name + show Places match to accept. |
| Promote to contact | `cards.promote_to_contact(fields)` `gcrm/tools/cards.py:173` | Reuse; pass `source="sign_scan"`. |
| Attach a person | `cards.promote_to_person(fields, contact_id)` `gcrm/tools/cards.py:213` → `save_person(...)` | Card path is single-person. Add `promote_people(contact_id, [people])` for the **N** people research finds (§7). |
| Enrichment agent + push | `cards.enrich_one(contact_id)` `gcrm/tools/cards.py:240` | Runs the enrichment agent (web search → `update_contact`) **and** already fires `send_push_to_all`. Reuse it as the deep-research step after Places resolution. |
| Places search | `google_maps_search(query, city, country)` `gcrm/tools/search.py:101` | Returns dicts with `name/address/website/phone` (+ more). Use for name+GPS → canonical business. |
| Web search / page fetch | `web_search`, `fetch_page` (used inside `enrich_one`) | Already wired into the enrichment agent. |
| Push notify | `send_push_to_all(title, body, data)` `gcrm/api/push.py:20` | Best-effort, never raises. `data={"screen":"contacts"}`. |
| Audit log | `log_audit(...)` (used throughout `api_cards.py`) | Log `sign.captured`, `sign.confirmed`, `sign.researched`. |

## 5. Data model

**Reuse the `card_captures` table** (`gcrm/db/migrations/023_card_captures.sql`) rather than adding a
new one. It already carries `gps_lat/gps_lng` (commented *"v2 storefront mode"* — this feature was
anticipated), the image/extraction columns, `dup_contact_id`, `contact_id`, and status fields.

**Migration `034_sign_capture_kind.sql`:**
- `ALTER TABLE card_captures ADD COLUMN IF NOT EXISTS kind VARCHAR(10) NOT NULL DEFAULT 'card';`
  (`'card' | 'sign'`).
- Optionally a `place_id VARCHAR` + `place_json JSONB` to record the resolved Google Place for
  provenance/debug.
- Contacts already have a `source` column (added in `023`); use `source='sign_scan'`.

Keep migrations idempotent (`IF NOT EXISTS`) — matches the existing style.

## 6. New vision prompt (`gcrm/prompts/signs.py`)

A sign is **not** a business card: expect a business name + maybe a logo/tagline, sometimes a phone
or URL, usually **no person and often no address**. Prompt Claude-vision to return JSON:

```
{ "is_sign": bool, "confidence": 0-100,
  "business_name": str|null, "business_type": str|null,   // short lowercase category if inferable
  "phone": str|null, "website": str|null, "tagline": str|null,
  "language": str|null, "note": str|null }
```

Rules to copy from `CARD_SYSTEM_PROMPT`: extract only what is visibly printed, never invent, `null`
for absent, set `is_sign=false` + explain in `note` if it's not a sign / unreadable. **Do not** ask
for a person's name (there rarely is one).

## 7. Backend build (`gcrm/`)

1. **`gcrm/prompts/signs.py`** — the prompt above.
2. **`gcrm/tools/signs.py`** (or extend `tools/cards.py` cleanly — prefer a new module to keep
   failure domains isolated):
   - `extract_sign_fields(image_bytes, media_type)` — parallels `extract_card_fields`.
   - `resolve_business(name, gps, country) -> dict|None` — call `google_maps_search` with the sign
     name; if GPS present, prefer the nearest/most-plausible Place. Return canonical
     `{name, address, city, website, phone, place_id}` or `None` if unresolved. **Degrade gracefully**
     when `GOOGLE_MAPS_API_KEY` is unset (returns `[]`) → fall back to the raw sign name.
   - `promote_people(contact_id, people: list[dict]) -> list[int]` — loop `save_person(...)` for each
     key person (name/title/email/phone), `source="sign_research"`. Best-effort per person; one
     failure must not abort the rest.
   - `research_business(contact_id)` — background entry point: (a) it may re-run `resolve_business`
     if needed, (b) call the existing enrichment agent to fill business details + **return key
     people**, (c) `promote_people(...)`, (d) `send_push_to_all("Business researched", ...)`.
     Model this closely on `enrich_one` (`tools/cards.py:240`) — likely `enrich_one` can be
     generalized/reused with a people-extraction step added.
3. **Enrichment agent people output** (`agents/gcrm-enrichment-agent/`): today it fills contact
   fields. Extend its node/prompt to also emit a `people: [{name, role, email, phone}]` list so
   `research_business` can persist them. Add/extend the agent's own tests (the CI runs each agent's
   test suite: `for a in research scout enrichment outreach followup; do ...`).
4. **`gcrm/api/routers/api_signs.py`** — parallel `api_cards.py`:
   - `POST /api/signs` — accept image + optional `gps_lat/gps_lng`, size-guard like
     `api_cards.py:47-53`, insert a `card_captures` row with `kind='sign'`, save image, run
     `extract_sign_fields`, return `{capture_id, is_sign, business_name, fields, dup_suggestion}`.
   - `POST /api/signs/{id}/confirm` — body = confirmed/edited business name (+ chosen Places match if
     you surface it). Call `resolve_business`, `promote_to_contact(source='sign_scan')` (reuse dup
     logic from `confirm_capture` `api_cards.py:150-160`), set capture `status='confirmed'`, then
     `background.add_task(signs.research_business, contact_id)`. Return `{contact_id, capture_id}`.
   - `POST /api/signs/{id}/discard`.
   - Register in `gcrm/api/main.py` (`app.include_router(api_signs.router)` near line 100).
   - Auth: use the same `require_jwt_admin` dependency as `api_cards.py`.
5. **Audit + retention:** `log_audit` on capture/confirm/researched. Honor the existing
   `CARD_IMAGE_RETENTION_DAYS` config for sign images too (delete on confirm when retention ≤ 0,
   like `api_cards.py:175`).

## 8. Mobile build (`engcrm-mobile/`)

1. **Drawer reorder** `app/(drawer)/_layout.tsx`: move the `contacts` `Drawer.Screen` to the top of
   the list; add a `scan-sign` screen labelled e.g. `"📷 Scan Sign"` near it. (Landing route is
   already Contacts via `app/index.tsx:15` — leave that.)
2. **`app/(drawer)/scan-sign.tsx`** — fork `capture.tsx`. Differences: request `expo-location`
   permission, get coordinates, pass `gps` to a new `captureSign()`; copy for signs ("Snap a
   storefront sign — we'll research the business"). Keep the offline-queue pattern only if cheap;
   otherwise a simpler online-only first version is acceptable (note it).
3. **`app/(drawer)/sign-confirm.tsx`** — slim confirm: show extracted business name (editable) and,
   if the backend returns a Places match, show name+address with **Accept / Reject** before creating
   the contact (guards against Places mis-resolution). On confirm, POST to `/api/signs/{id}/confirm`,
   then `Alert` "Researching in the background — you'll get a notification," and navigate to Contacts.
4. **`services/api.ts`**: add `captureSign(imageUri, gps)`, `confirmSign(captureId, fields, ...)`,
   `discardSign(...)` — parallel the card functions (`services/api.ts:167-195`). Reuse the multipart
   note (don't set `Content-Type`).
5. **Types**: add `SignCaptureResult` / `SignFields` interfaces alongside the card ones.
6. **Tests**: mirror `engcrm-mobile/__tests__/` for the new screen + api functions. CI gate
   (`android.yml`) runs typecheck + lint + `npm audit --omit=dev --audit-level=high` + jest — all
   must pass.

## 9. GDPR (do not skip — this is part of the work)

Sign research collects **third-party personal data** (key people's names/emails/phones) — more
sensitive than a card someone handed over. Chris actively maintains
`docs/gdpr/art30-processing-record.md`.

- Add an **Art. 30 processing entry** for "storefront-sign business research" (purpose, categories of
  data + data subjects, lawful basis = legitimate interest for B2B outreach + a short balancing note,
  retention, recipients).
- **Retention:** reuse `CARD_IMAGE_RETENTION_DAYS` for sign images; decide/record retention for
  researched People rows.
- Record provenance via `contacts.source='sign_scan'` and People `source='sign_research'` (already
  supported) so erasure/export can find sign-sourced data.

## 10. Risks / guardrails

- **Places mis-resolution:** a sign reading just "Müller" + logo is ambiguous even with GPS. The
  confirm screen must let the user accept/reject the Places match **before** a contact is created —
  otherwise the CRM fills with wrong businesses.
- **Missing Places key:** flow must degrade to web-search-only, not error.
- **Cost:** Places (New) bills per call; set a billing cap. Vision + enrichment already cost per scan
  (tracked in `extraction_cost_usd`) — record sign costs the same way.
- **Push is best-effort:** never let a failed notification fail the research job (existing code
  already isolates this).

## 11. Suggested PR order (respects the auto-deploy + migration ordering)

1. **PR A — infra prep (done):** `GOOGLE_MAPS_API_KEY` is set and working locally **and** on the VPS
   (verified). Only remaining nicety: add a documented placeholder line to `.env.example`. Not a
   blocker — fold it into PR B.
2. **PR B — backend, migration first:** migration `034` + `prompts/signs.py` + `tools/signs.py` +
   enrichment-agent people output + `api_signs.py` + tests + Art. 30 entry. Deploys to VPS on merge.
3. **PR C — mobile:** drawer reorder + `scan-sign.tsx` + `sign-confirm.tsx` + `services/api.ts` +
   tests. (Laptop runner must be on for the build.)

Mobile can technically ship before the backend (endpoints just 404 until then), but landing backend
first gives a working end-to-end demo.

## 12. Done-when (verification, per house standards)

- Backend: `uv run ruff check .` clean; `uv run pytest tests -q` + each agent suite green; new
  unit tests cover `extract_sign_fields`, `resolve_business` (incl. no-key fallback), `promote_people`.
- Mobile: `npm run typecheck`, `npm run lint`, `npm test` green.
- Manual e2e on a real device: photograph a real storefront sign → confirm the Places match → receive
  the "Business researched" push → the contact appears in Contacts with linked People, business
  description, and (when available) email/phone/website.
- GDPR: Art. 30 record updated; provenance + retention verified for a sign-sourced contact.
