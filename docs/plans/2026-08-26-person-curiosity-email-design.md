# Person First-Contact ("Curiosity") Email

**Date:** 2026-08-26

## Goal

A one-off, non-sales first-contact email, sent to a specific *person* (not a
company): introduce Christopher briefly with a fixed opening, note the
business isn't open until October 1, 2026, make one genuine observation about
that person/their company, then ask for their perspective on how AI will
affect their field — no pitch, no CTA. This is deliberately a different tone
from the existing mission-driven sales outreach in `gcrm/prompts/outreach.py`
(`draft_email_prompt`), which stays untouched.

Lives on `person_detail.html` because the target is always a named individual
— never an organization — matching how the rest of the person-vs-organization
split already works in this app.

## Why not the existing approval queue

`approval_queue` / `approval.html` / `drafts.html` are hard-wired to
`contacts` (organizations): the send step reads `contact.email`, logs to
`interactions`, and updates `contacts.status`. Retrofitting that shared table
to also carry people would mean a schema migration (nullable `contact_id`,
new `person_id`, a one-of constraint) plus changes across the routers behind
the primary sales pipeline. Too much blast radius for a one-off, admin-only,
one-person-at-a-time email. Instead this reuses the pattern already proven on
this exact page for dictated notes: generate → editable review box → save,
no persisted "pending" row.

## Non-goals (YAGNI)

- No persisted draft/queue row — regenerate if you navigate away before
  sending. Nothing here is scored, scheduled, or run in bulk.
- No i18n — the fixed opening line is English, so the whole template is
  English-only for now.
- No changes to `approval_queue`, `draft_email_prompt`, or the sales-outreach
  pipeline.
- No opt-out / privacy-notice footer — those are compliance boilerplate for
  the scored sales pipeline; this is a manual, individually-reviewed email an
  admin sends one at a time.
- No mobile UI — web only, matching the person-add and interaction-log
  precedent.

## Template — English and German, selectable

Fixed parts live in a small `CURIOSITY_TEMPLATES = {"en": {...}, "de": {...}}`
dict in `gcrm/tools/curiosity_email.py` (Python strings, not LLM-authored —
see rationale below), each with `greeting`, `opening` (intro + Oct 1 line),
`ask`, `closing`, `signoff`, `subject`, `field_fallback`:

```
{greeting}

{opening}

{llm_observation}

{ask}

{closing}

{signoff}
```

English `opening`: "My name is Christopher Rehm and I'm building an AI
focused business, to assist businesses improve their regular workflows so
they can focus on the key parts of their operation. I'm not open yet — I'll
be starting October 1, 2026."

German `opening`: "Mein Name ist Christopher Rehm, und ich baue gerade ein
auf KI fokussiertes Unternehmen auf, das Unternehmen dabei hilft, ihre
laufenden Arbeitsabläufe zu verbessern, damit sie sich auf die wichtigsten
Teile ihres Betriebs konzentrieren können. Ich bin noch nicht im Geschäft —
ich starte am 1. Oktober 2026." (formal *Sie*, matching the register already
used in `outreach.py`'s German opt-out/privacy lines.)

`{field}` = `organization.type` if the person is linked to a company, else
`person.title`, else the language's `field_fallback` ("your line of work" /
"Ihrem Bereich"). `{first_name}` = first word of `person.name`.

Only `{llm_observation}` (1-2 sentences) comes from the LLM, generated in the
selected language — asking an LLM to reproduce a fixed personal introduction
verbatim across every generation is a needless reliability risk when Python
can just guarantee it.

**Language selection**: a `<select>` (English/German) next to the draft
button on `person_detail.html`, sent as `?language=en|de` to the draft route.
Default: the linked organization's `preferred_language` if the person has
one, else `"en"` (no per-person language field exists to key off otherwise).

## Backend

**`gcrm/prompts/curiosity_email.py`** (new):

```python
def draft_curiosity_observation_prompt(person: dict, organization: dict | None, recent_notes: list[dict], language: str) -> tuple[str, str]:
    """System/user prompt: return JSON {"observation": str} — one or two
    specific, genuine sentences (not flattery), written in `language`
    ("en"/"de"), about this person or their business, drawn from whatever
    context is available. Same null-for-absent discipline as the other
    extraction prompts: if there's nothing specific to say, produce a brief
    honest sentence from the person's role/company rather than inventing
    detail."""
```

**`gcrm/tools/curiosity_email.py`** (new, mirrors `email_extract.py`):

```python
def draft_curiosity_email(person_id: int, language: str = "en") -> dict:
    """Loads the person (+ linked organization if contact_id is set, + up to
    5 recent people_interactions), generates the observation via
    get_llm(SMART_LLM) in the given language, and assembles the matching
    CURIOSITY_TEMPLATES[language] around it. Returns {"subject": str, "body":
    str} or {"error": <fixed client-safe string>} — real exception goes to
    the log, mirroring extract_person_from_email. Raises LookupError if the
    person doesn't exist."""
```

**`gcrm/api/routers/people.py`** gains two admin-only routes:

- `POST /people/{person_id}/curiosity-email/draft?language=en|de` — no DB
  write, calls `draft_curiosity_email`, returns `{"subject", "body"}` or
  `{"error"}`.
- `POST /people/{person_id}/curiosity-email/send` — JSON body
  `{"subject": str, "body": str}` (the possibly-edited draft). Calls
  `send_email(person.email, subject, body)`; on success, calls
  `log_person_note(person_id, method="email", note=f"Sent: {subject}")`
  (from `db_people_interactions.py`) so it shows up in that person's
  timeline, and `log_audit`. Returns `{"sent": bool}`. A person with no email
  on file returns 400 before attempting to send.

## Frontend

`person_detail.html` gains a new section below the existing notes/interaction
log: a language `<select>` (English/German, defaulted per the rule above) and
a "Draft first-contact email" button. Clicking it POSTs to the draft route
with the selected language and fills an editable subject `<input>` + body
`<textarea>` (same review-before-save shape as the dictation flow's
transcript box). A "Send"
button POSTs the current (possibly hand-edited) subject/body to the send
route; on success it clears the draft and the page's interaction table gets
the new entry on next load (reload after send, matching how the notes-save
flow already reloads).

New i18n keys in `en.json` (+ `de.json` for consistency with the rest of the
page, even though the email body itself stays English):
`personDetail.curiosityEmail.title`, `.draftButton`, `.drafting`,
`.draftFailed`, `.subjectLabel`, `.bodyLabel`, `.sendButton`, `.sending`,
`.sendSuccess`, `.sendFailed`, `.noEmail`.

## Error handling

- **No email on file**: draft still generates (useful to review/copy
  manually), but the Send button is disabled with `personDetail.
  curiosityEmail.noEmail` shown instead.
- **LLM/generation failure**: fixed client-safe string, real exception
  logged, same as `extract_person_from_email`.
- **Send failure** (`send_email` returns `False` — SMTP error or
  `EMAIL_ENABLED=false`): fixed client-safe string, no interaction logged
  (only a real send gets logged), admin can retry.

## Testing

New `tests/test_people_curiosity_email.py`:
- `draft_curiosity_email` unit tests: person-only context, person + linked
  org context (mocking `get_llm`), LLM failure → fixed error string,
  `LookupError` for a missing person.
- Route tests: both routes require admin; draft route returns
  subject/body on success and the fixed error on failure; send route calls
  `send_email` with the edited body (not a re-generated one), logs a
  `people_interactions` row only on successful send, 400s when the person has
  no email.
- Template test mirroring
  `test_organization_template_has_accessible_analysis_progress_feedback`:
  asserts the new data-attributes and aria-busy wiring are present.
