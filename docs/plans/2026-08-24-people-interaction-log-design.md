# People Interaction Log (Dictated Notes)

**Date:** 2026-08-24

## Goal

`people` (individual collectors/contacts) currently has one flat `notes` text
field and no history — every dictated update overwrites the last one. This
adds a timestamped log of short notes per person, capturable either by typing
or by recording a voice memo that gets transcribed for review before saving.
Entry point is always a specific person's detail page (web or mobile) — never
a dictate-first-then-guess-who flow, since the person is always already known
by the time you're adding a note.

Transcription reuses the existing self-hosted Whisper pipeline
(`gcrm/tools/transcribe.py`) already powering the organization voice-memo
flow (`gcrm/api/routers/api_voice.py`) — no new transcription infra. Unlike
that flow, there is no LLM structuring step and no candidate/name matching:
the person is fixed, so raw transcript → editable review box → save is the
whole pipeline.

## Non-goals (YAGNI)

- No editing a saved entry — delete-and-redictate only (soft delete via
  `deleted_at`, matching `interactions`).
- No candidate/name matching or dictate-first flow — always initiated from a
  known person.
- No migrating the existing `people.notes` field into the log — `notes`
  stays as a general free-text field (static facts); the log is strictly the
  dated interaction history. Both coexist.
- No LLM transcript structuring (summary/follow-up extraction) — that's the
  org voice-memo flow's job, not this one.
- No mobile "confirm" screen as a separate route — review-and-save happens
  inline on `person-detail.tsx` in an expanding panel, one screen not two.
- No export/reporting on this log yet.

## Data model

New table, mirroring `interactions` but scoped to `people`:

```sql
CREATE TABLE people_interactions (
    id          SERIAL PRIMARY KEY,
    person_id   INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    method      VARCHAR(20),   -- call | visit | email | other
    note        TEXT NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    deleted_at  TIMESTAMPTZ
);
CREATE INDEX idx_people_interactions_person_id
    ON people_interactions(person_id) WHERE deleted_at IS NULL;
```

`occurred_at` is a timestamp, not a date, since "date and time" was explicit
in the ask and a dictated note has no separate "what happened vs. when I
logged it" distinction worth modeling as two columns.

## Backend

**`gcrm/tools/db_people_interactions.py`** (new, mirrors `db_interactions.py`):

```python
def log_person_note(person_id: int, method: str | None, note: str) -> int:
    """Insert a note, touch people.updated_at, log_audit. Returns the new row id."""

def get_person_interactions(person_id: int) -> list[dict]:
    """Newest first, deleted_at IS NULL."""

def delete_person_interaction(interaction_id: int) -> None:
    """Soft delete: sets deleted_at."""
```

**`gcrm/api/routers/api_people_interactions.py`** (new), used by both web and
mobile:

- `POST /api/people/{person_id}/notes/transcribe` — multipart audio upload →
  `{"transcript": str}`. Calls `transcribe()` directly, no LLM structuring.
  Same guards as `api_voice.py`: `MAX_UPLOAD_BYTES`, fixed client-safe error
  string on failure (`"Couldn't make out any speech — try again or type your
  note."`), real exception to the log.
- `POST /api/people/{person_id}/notes` — JSON `{"note": str, "method": str |
  None}` → `log_person_note(...)`, returns the new entry.
- `GET /api/people/{person_id}/notes` — list for mobile's timeline.
- `DELETE /api/people/{person_id}/notes/{note_id}` — soft delete.

Web uses session-cookie auth (`require_login`, matching the rest of
`people.py`); mobile uses `require_jwt_admin` (matching `api_voice.py`) — the
router takes both since the person-detail page is server-rendered for web
but these are still JSON API routes hit via `fetch()`/mobile client.

## Web UI

`person_detail.html` gets a new section below the existing `notes` textarea:
a "🎙 Record note" button using the browser `MediaRecorder` API (new
client-side code — no existing precedent on web) to capture audio, POST to
the transcribe endpoint, then drop the result into an editable `<textarea>`
with a method `<select>` (call/visit/email/other) and a Save button that
POSTs to the notes endpoint. Below that, existing entries render
server-rendered (Jinja, matching the rest of this page — no SPA framework):
timestamp + method + note, newest first, each with a small delete link.

## Mobile UI

`person-detail.tsx` gains a record button reusing the exact pattern already
in `voice.tsx` (`useAudioRecorder(RecordingPresets.HIGH_QUALITY)`,
`requestRecordingPermissionsAsync`, `setAudioModeAsync`), plus the timeline
list fetched from `GET .../notes`. Recording, transcribing, and the
review/save panel all live inline on this one screen — no navigation to a
separate confirm route.

## Error handling

- **Mic permission denied / no mic**: inline fallback message + plain text
  input so dictation is an accelerator, never a hard requirement.
- **Transcription fails or returns empty**: fixed client-safe error string,
  real exception logged server-side, review box stays empty for manual
  typing.
- **Audio too large / unauthenticated**: reuse `MAX_UPLOAD_BYTES` and the
  existing auth dependencies exactly as `api_voice.py` does.

## i18n

New keys in `gcrm/i18n/en.json` + `de.json`: `personDetail.notes.record`,
`.transcribing`, `.save`, `.delete`, `.methodCall`, `.methodVisit`,
`.methodEmail`, `.methodOther`, `.micNeeded`, `.transcribeFailed` — every
other string on this page already goes through `t()`.

## Testing

`tests/test_people.py` (or a new `tests/test_people_interactions.py`)
mirrors `tests/test_voice.py`: `db_people_interactions.py` unit-tested with a
mocked `db()`; the router tested with `transcribe` mocked (happy path, empty
transcript, too-large upload, auth required for both cookie and JWT paths);
one test confirming a soft-deleted entry doesn't reappear in
`get_person_interactions`. No mobile test harness precedent exists for
`voice.tsx`, so mobile ships without tests, consistent with the rest of that
app.
