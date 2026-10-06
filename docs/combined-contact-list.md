# Combined Contacts list

The mobile app and website now offer a Contacts list combining people and
organizations, ordered by when each record was added. Existing separate lists
remain available. A type label distinguishes each row and opens its corresponding
detail screen.

The mobile drawer entry is Contacts. The website navigation links to
`/contact-feed/`; legacy `/contacts/` organization redirects remain intact.
Both clients use the same query through `/api/contact-feed` and the web router.

## Behavior

- Default order: newest added first. Alphabetical order is also available.
- Search matches name, role/category, company, city, email or phone. Each of up
  to four search words must match; SQL wildcard characters are treated literally.
- Contact type and pipeline stage filters apply across the combined list.
- Paging selects 50 rows from one mixed result set. Type plus ID identifies each
  row, preserving people and organizations with the same numeric ID.
- Mobile supports pull-to-refresh and incremental loading. Website paging retains
  the active query and filters; signed session state remembers filters on return.
- Deleted records are excluded. Requests from real accounts are scoped to their
  workspace; company metadata on person rows cannot leak from another workspace.
- English and German labels follow the existing list styles. No new dependency
  or migration is needed.

## Verification

- Backend: 1,191 tests passed against disposable PostgreSQL 16 with the existing
  network exclusion (one network test deselected).
- Mobile: 257 tests passed in 36 suites; TypeScript and ESLint passed.
- Ruff and whitespace checks passed.
- New query tests cover mixed chronology, tie order, colliding IDs, combined
  pagination, deleted rows, workspace boundaries, literal search and stage/type
  filters against the real database.
- End-to-end server coverage creates an organization and linked person through
  the mobile API, signs into the website, browses the mixed list, opens both
  kinds of detail page and returns with the search retained.
- Mobile screen coverage checks both detail destinations, filter combinations,
  pagination identity, empty/error states and refresh recovery.
- One initial mobile test expected `Couldn't load. Pull down to refresh.` instead
  of the existing catalog text `Couldn't load — pull down to refresh`. The exact
  assertion was corrected to the catalog; the same error/recovery checks passed.

Validation was local. Physical-device testing and deployed availability require
release of this commit. The mobile screen will require an updated app build.
