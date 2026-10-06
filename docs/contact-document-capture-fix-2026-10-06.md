# Letters through the mobile contact scanner

The previous document-scanner release (`4a9d14f`) did not reach the backend or
Android app. Both release workflows stopped at their dependency audits:
[backend](https://github.com/johnfire/engcrm/actions/runs/37490358855) and
[Android](https://github.com/johnfire/engcrm/actions/runs/37490358910).
The release-blocker fixes are already committed locally in `f077371`.

The older Scan Card flow explicitly told vision to reject anything that was not
a business card. A photographed letter therefore produced the reported rejection,
even when its signature contained readable contact details.

## Behavior after this fix

- Scan Contact accepts a business card or a document containing a primary contact.
  The existing `/api/cards` response remains compatible with installed clients.
- Letter extraction reads the sender/signatory together with their organization's
  matching footer or letterhead. Legal boilerplate directors are not substituted
  for that person. Instructions printed in the image remain source text.
- Documents are staged with `kind=document`. Review saves the organization and
  linked person with `source=document_capture`; a failed person save leaves the
  draft available for retry. Capture itself does not create the lead.
- The updated mobile app preserves the complete photo, without the old editing
  crop, and uses the existing 2048-pixel document preparation. A button opens the
  multi-contact document scanner for directories and lists.
- Extraction and capture audit events distinguish the vision agent from the user
  and carry the request correlation ID.

## Validation

- Backend: 1,166 tests passed against a disposable PostgreSQL 16 database, using
  the existing network exclusion. After the final audit-context changes, all 36
  capture/document tests passed again.
- Mobile: 250 tests passed across 34 suites; TypeScript and ESLint passed.
- Ruff and whitespace checks passed.
- The new database flow test uploads a letter through `/api/cards`, checks that
  it is pending review, confirms it, and verifies organization address, phone,
  website, person name, role, email, link, provenance and audit actors.
- Mobile tests cover camera/library capture, review handoff, unreadable text,
  permission denial, offline retention, rejected requests, cancellation and the
  multi-contact entry point.
- The first mobile run found four existing shell-quote security test failures
  because this checkout's installed dependencies preceded `f077371`. Reinstalling
  from the committed lock resolved them without changing the tests.
- Mobile release audit passed with zero critical findings (55 high and 14 moderate
  findings remain). Backend audit passed with no known vulnerabilities; local
  project packages are unpublished and cannot be checked against the PyPI advisory database.

The supplied photo has not been sent to the external vision service: automatic
approval review requires explicit approval for that particular image. No contact
from this photo has been inserted into production. Local tests use mocked vision
responses and a disposable database; they do not establish physical-phone or live
model accuracy. Pushing the local commits and successful release workflows remain
necessary before this fix is available on the phone.
