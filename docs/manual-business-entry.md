# Manual business entry

Admins can choose **Add business** from Contacts or Organizations on the website
and mobile app. Name is required; city, country, type, email, phone, website,
decision maker, preferred contact method and notes are optional. Country defaults
to DE when omitted. The form offers all six pipeline stages, initially Candidate.
Saving uses the selected stage and opens the new organization's details.

The website form at `/organizations/new` and mobile `POST /api/contacts` share
validation and duplicate detection. A duplicate name/city or email offers the
existing record without overwriting it. Deleted duplicates and ignored chains
are reported without an inaccessible detail link. Website errors preserve the
entered fields and stage. New records carry `source=manual`; audit events retain
the requesting user's identity and correlation ID. Existing mobile clients that
omit the stage continue to create Candidates. Spectators cannot create businesses.

Verified locally on 2026-10-06:

- Backend: 1,215 tests passed, including real PostgreSQL persistence for every
  stage, duplicate protection, audit attribution, and web/mobile creation flows.
  One live-service test was excluded with the standard `not network` selection.
- Mobile: 260 tests passed; TypeScript and lint passed.
- Python lint and diff checks passed.
- Website form visually checked at desktop and 390px widths.

Physical-device testing and production rollout remain unverified. This feature
and the preceding combined Contacts screen are committed locally, awaiting push.
