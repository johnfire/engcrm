# Manual + Email-Extracted Person Add

**Date:** 2026-08-24

## Goal

There's currently no way to add a person (individual collector/contact) from
the web app at all — `people` rows only get created via the mobile
business-card scan flow (`gcrm/tools/cards.py` → `promote_to_person`). This
adds a `+ Add person` page to the web app with two ways to fill it in: type
the fields by hand, or paste raw email text (body/signature) and have an LLM
extract name/email/phone/etc. into the same fields for review before saving.

Both paths end at the same save step, so there is exactly one place a person
row gets created from the web: a human always sees and can edit the fields
before they're written, matching the confirm-before-save pattern the card
flow already established.

## Non-goals (YAGNI)

- No inbox polling / forward-to-address / .eml upload — paste-the-text is the
  only email input mechanism (confirmed with Chris).
- No linking to a company `contact` on create — the existing edit form
  deliberately excludes `contact_id` from `EDITABLE_COLUMNS` ("the company
  link is a relation, not a text field"); the new-person form follows the same
  rule and leaves `contact_id` NULL.
- No background enrichment task — that's a card-flow behavior tied to
  `contacts`/company enrichment, not applicable to a bare person row.
- No mobile UI — web only.

## Backend

**`gcrm/tools/email_extract.py`** (new, mirrors `cards.py`'s extraction half):

```python
def extract_person_from_email(text: str) -> dict:
    """Runs get_llm("claude-haiku") on raw email text, returns
    {"fields": {...}, "model": str, "cost_usd": float}."""
```

Same shape as `extract_card_fields`: `parse_llm_json` on the response,
`_usage_cost` for cost tracking, a fixed client-safe error string on failure
(`"Could not read this. Enter the details manually."`) — the real exception
goes to the log, never to the response. No image handling, no `is_card`
flag — text in, JSON out.

**`gcrm/prompts/person_email.py`** (new): system prompt telling the model to
pull `name`, `title`, `company`, `email`, `phone`, `website`, `city`,
`country` from an email body/signature block, same null-for-absent /
never-invent discipline as `CARD_SYSTEM_PROMPT`.

**`gcrm/api/routers/people.py`** gains two routes:

- `POST /people/extract-email` — admin-only, JSON body `{"text": str}` →
  `{"fields": {...}}` or `{"error": str}`. No DB write. Mirrors the
  `fetch()`-from-a-template pattern already used in `areas.html`
  (`POST /areas/scan`) — no CSRF token needed since none of the existing POST
  routes use one (session cookie + same-origin fetch).
- `GET /people/new` — renders the new `person_new.html` form (blank).
- `POST /people/new` — same field set as `person_edit`, requires `name`,
  calls `save_person(...)` (dedup by email/name already built in), logs
  `person.created` via `log_audit`, redirects to `/people/{id}?saved=1`.

`people.html` gets a `+ Add person` link in the page header next to the
existing search bar, pointing at `/people/new`.

## Frontend

**`gcrm/ui/templates/person_new.html`** — same `detail-grid` / `field-row`
structure as `person_detail.html` (name, title, relationship, email, phone,
website, city, country, met_at, notes), reusing the same `person-*` element
ids and i18n keys so the two templates stay visually identical. Above the
form: a textarea + "Extract from email" button. Its inline `<script>` (same
style as `areas.html`) POSTs the textarea content to
`/people/extract-email`, then fills the form inputs by id from the returned
`fields` — the user reviews/edits before hitting the existing `Save` button,
which does a normal form POST to `/people/new`.

New i18n keys (`gcrm/i18n/en.json` + `de.json`): `people.addPerson`,
`personNew.title`, `personNew.pasteEmailLabel`, `personNew.extractButton`,
`personNew.extracting`, `personNew.extractFailed`.

## Testing

`tests/test_people.py` gains: `extract_person_from_email` unit tests (success
parse, malformed-JSON fallback, exception → fixed error string — same
structure as the existing `TestPromoteToPerson` tests, mocking `get_llm`),
`POST /people/extract-email` route tests (auth required, success, extraction
failure surfaces the fixed string), and `POST /people/new` route tests
(creates via `save_person`, blank name → 400, redirects to the new person's
detail page) — mirroring `TestUpdatePerson` / `TestPersonDetailPage` already
in that file.
