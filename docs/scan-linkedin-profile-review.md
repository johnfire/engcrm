# LinkedIn profiles during Android scan review

Implemented locally on 2026-10-08. Requires the updated backend and Android app
before it appears on the phone.

The shared card/document review screen automatically searches public web indexes
using the scanned person's full name, company, and city. It shows up to three
personal LinkedIn profiles with the search title and snippet. The user opens a
profile to check it, chooses **Use this profile**, or pastes a URL. Saving the
contact persists that chosen URL in `people.linkedin_url`. A URL visibly printed
on a card or paper is also extracted into the editable review field.

Names must have at least two words for automatic lookup. Company-only scans skip
the search. Results are suggestions, not verified identities. No matching result
does not establish that someone has no LinkedIn page. Search errors leave the
contact import available; stale responses are ignored when the identity changes.
Company pages and unrelated domains are rejected. Existing different profile
links cause a review conflict and keep the scan pending instead of replacing the
saved identity. A profile link does not mark the person as a LinkedIn connection.

The lookup uses the existing `ddgs` dependency with a bounded request timeout;
it does not require an Android LinkedIn login or a new paid API. See the
[DDGS reference](https://github.com/deedy5/ddgs) and the project's required
[Expo SDK 56 reference](https://docs.expo.dev/versions/v56.0.0/).

## Entry provenance already present

| Record | Origin information | Dates |
| --- | --- | --- |
| Person (`people`) | `source`, e.g. `card_capture`, `document_capture`, `manual`, `linkedin_import` | `created_at`, `updated_at` |
| Organization (`contacts`) | `source`, e.g. `card_capture`, `document_capture`, `manual`, `sign_scan` | `created_at`, `updated_at` |
| Scan (`card_captures`) | `kind`, `captured_by`, extracted/reviewed fields, organization link; document batch and row when relevant | `captured_at`, `created_at`, `updated_at` |
| Audit (`audit_log`) | actor, actor type, action, target, outcome, correlation ID | `at` |

The existing person detail page shows source and date added. Source is nullable:
legacy rows and some research inserts may have no origin label, so it is not a
complete source history for every historical entry. Rescanning an existing
person preserves their original source and creation date.

This change adds `person.capture_confirmed` audit entries that link the person to
each confirmed capture, and `person.linkedin_saved` entries for the selected
profile. Lookup attempts have `capture.linkedin_searched` audit entries, including
their result status and request correlation ID. Capture actor and workspace are
set in the request handler; profile lookups and saving enforce workspace scope.

## Verification

- Backend regression suite: 1,306 passed, with one pre-existing network test
  excluded by the normal non-network selection. Final focused backend checks
  after the last edits: 177 passed.
- Mobile regression suite: 278 passed. Final scan/profile checks after the last
  edits: 11 passed. TypeScript, ESLint, Ruff, and whitespace checks passed.
- Real PostgreSQL tests cover card and document upload, lookup, review, saving,
  stored profile retrieval, source/date preservation, conflicts, and isolation.
- Mobile tests cover explicit profile selection, pasting/removal, retry, skipped
  company-only scans, stale lookup responses, and disabled selection while saving.
- A real search lookup found the indexed personal profile for Satya Nadella;
  no CRM records were created by that check.
- Physical Android camera use and a release build have not been verified.
