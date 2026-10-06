# Grouped Contacts list

Contacts on mobile and the website shows one row per business, with its contacted
people in an expandable list underneath. The business's last contact day is the
latest actual contact with the business or any linked person. A person without an
active business in the same workspace appears as a standalone row. Records with
no actual contact history are hidden; People and Organizations still include them.

Grouping uses the explicit person-to-business link, not a guessed company name.
It changes the list presentation without merging records or interactions. Opening
a business or person continues to show that record's own details and history.

The mobile drawer entry is Contacts. Website navigation links to `/contact-feed/`;
legacy `/contacts/` organization redirects remain intact. Both clients use the
same database query. The older API sort key `newest` now means last contact;
existing signed website filter settings are upgraded to `last_contact`.

## Contact dates

- Organization contact days come from `interactions.interaction_date`. Person
  contact days come from `people_interactions.occurred_at`, in Europe/Berlin time.
  Deleted interactions and next-step planning/completion entries do not count.
- Last contact is the maximum actual interaction day across a business and its
  contacted people. People inside a group are sorted by contact day, then ID.
  A direct business contact wins a same-day tie with a person; the highest person
  ID breaks ties between people. List rows use a stable type/ID tie order.
  Alphabetical order remains available.
- Business rows identify the person supplying the latest date when applicable.
  The row's date editor opens that person's actual interaction, rather than
  changing an older direct business interaction. Each expanded person also has
  their own date link. Correcting a date recomputes the group and its list order.
  Detail-screen editors continue to edit that individual record's history.
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

- Search matches the business or any contacted linked person's name, role,
  city, email or phone, as well as standalone people's company text. Each of up
  to four words must match; SQL wildcard characters are treated literally.
- Type choices are All contacts, Organization and People without business.
  Stage filtering applies to the business stage for groups and the person's
  stage for standalone rows. It does not remove people from a matching group.
- Paging selects 50 complete groups or standalone rows. Linked people are grouped
  before pagination, so a group cannot split across pages. Type plus ID preserves
  colliding numeric IDs.
- Mobile supports refresh and incremental loading, and reloads on returning from
  the date editor. Website paging retains signed query/filter selections.
- Deleted records are excluded. Accounts are scoped to their workspace, including
  company metadata on person rows. Labels are available in English and German.
- No dependency or database migration was added.

## Verification — 2026-10-06

- Full backend suite: 1,242 passed against disposable PostgreSQL 16; one
  live-service test was deselected using the established `not network` selection.
- Final integration checks: nine passed, including additional cross-workspace
  linked-person isolation and differing business/person stage coverage.
- Full mobile suite: 271 passed in 38 suites. TypeScript and ESLint passed.
- Python lint and whitespace checks passed. The website's expandable grouped
  list was visually inspected with representative sample records.
- Coverage includes business-only/person-only history, latest-source date edits,
  backdating and reordering, same-day ties, local midnight boundaries, deleted
  and cross-workspace business links, planning/deleted interactions, complete
  groups with more than 50 people, global pagination, search and saved filters.
- Mobile coverage checks expansion/collapse, business/person navigation, latest
  source editing, standalone records, viewers, refresh and incremental loading.

Validation was local. Physical-device behavior and production availability remain
unverified until release; mobile requires an updated app build.
