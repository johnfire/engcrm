# Combined Contacts list

Contacts on mobile and the website combines people and organizations you have
contacted. It orders them by the most recent recorded contact day, rather than
when a record was added. Records with no contact history are hidden; the separate
People and Organizations lists continue to include them.

The mobile drawer entry is Contacts. Website navigation links to `/contact-feed/`;
legacy `/contacts/` organization redirects remain intact. Both clients use the
same database query. The older API sort key `newest` now means last contact;
existing signed website filter settings are upgraded to `last_contact`.

## Contact dates

- Organization contact days come from `interactions.interaction_date`. Person
  contact days come from `people_interactions.occurred_at`, in Europe/Berlin time.
  Deleted interactions and next-step planning/completion entries do not count.
- Last contact is the maximum actual interaction day. Equal days use a stable
  type/ID tie order. Alphabetical order remains available.
- Admins can open **Last contact date** from mobile rows and both detail screens,
  or **Change date** on website rows. Website detail screens also link to the editor.
- The editor corrects the most recent actual interaction. If no contact has been
  logged yet, it records a first contact on the selected day. No stage or status
  changes are implied. Mobile offers Today, Yesterday and Two days ago shortcuts,
  plus manual date entry; the website uses its native date input.
- Corrections preserve the person's recorded local time and the original entry's
  creation timestamp. If another interaction is now more recent, that interaction
  becomes the last contact. Correcting a date does not add a duplicate entry.
- A stale history ID/day is rejected with a conflict. Reopening the editor loads
  the current history. Failed saves keep the entered date, including on mobile.
- The server rejects invalid and future dates. All edits require admin access,
  check workspace ownership, and record actor/correlation IDs in the audit log.

## Browsing

- Search matches name, role/category, company, city, email or phone. Each of up to
  four words must match; SQL wildcard characters are treated literally.
- Type and pipeline stage filters apply across the list. Paging selects 50 rows
  from one mixed result set; type plus ID preserves colliding numeric IDs.
- Mobile supports refresh and incremental loading, and reloads on returning from
  the date editor. Website paging retains signed query/filter selections.
- Deleted records are excluded. Accounts are scoped to their workspace, including
  company metadata on person rows. Labels are available in English and German.
- No dependency or database migration was added.

## Verification — 2026-10-06

- Full backend suite: 1,235 passed against disposable PostgreSQL 16, with one
  live-service test excluded using the established `not network` selection.
- Final targeted backend checks: 15 passed, including the additional stale web
  form check ensuring a retry cannot silently retarget a newer interaction.
- Full mobile suite: 269 passed in 38 suites. After the final keyboard/scroll
  adjustment, six date-editor checks passed again. TypeScript and ESLint passed.
- Python lint and whitespace checks passed. Website list and date editor were
  visually inspected; the date form also fits a 390px viewport.
- Coverage includes history-backed ordering independent of creation date, missing
  contacts, planning/deleted history, date corrections, preserved local times,
  midnight boundaries, duplicates, stale forms, permissions, workspace isolation,
  mixed pagination, saved filters and shared web/mobile history.

Validation was local. Physical-device behavior and production availability remain
unverified until release; mobile requires an updated app build.
