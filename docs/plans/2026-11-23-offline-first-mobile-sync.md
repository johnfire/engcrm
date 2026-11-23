# Offline-first mobile storage and synchronization

Date: 2026-11-23 · Status: approved plan, not started

## Goal

The Android app should open organizations, people and the combined Contacts list from
local storage immediately, whether or not the server is reachable. Ordinary work done on
the phone must also work offline and synchronize later.

PostgreSQL remains the durable system of record. When the same field is changed in more
than one place, the value saved most recently by the user wins, even when an older or newer
phone edit reaches the server out of order.

This is an offline-first design, not a response cache. The phone has a real local database,
an outbox of unsynchronized mutations and a deterministic reconciliation protocol.

## Decisions agreed with Chris

| Question | Decision |
|---|---|
| Local coverage | Store every active organization, person and deal needed by the Organizations, People and Contacts screens. Store their activity/note history so their detail pages remain useful offline. Contacts is a local projection of organizations and people, not a second editable copy. |
| Offline writes | Create organizations and people; create their initial deal when the quick-create flow selects an offer; edit ordinary fields; edit an existing deal's stage, status and next step; add organization activities and person notes. |
| Web-only operations | Deleting records, merging duplicates, adding or removing an additional deal, sales, subscriptions and other high-impact administration. |
| Conflict rule | Last edit wins **per field**, ordered by the time the user pressed Save. Arrival order does not decide the winner. |
| Clocks | Phone and server clocks are trusted as internet-synchronized. A clearly future-dated phone mutation is stopped and shown as an error rather than silently changing its time. |
| Deleted target | A later phone edit never restores a record automatically. It becomes a provisional change for review on the web. |
| Provisional retention | Keep the proposed values for 30 days, then purge them. |
| Erasure exception | A GDPR-erased record cannot be restored or retained in a provisional payload. The phone mutation is discarded and the phone is told to remove its local copy. |
| Delivery | Server support first, then read-only local storage, then offline writes, then the web review queue. Every phase is deployable and reversible without losing acknowledged changes. |

No product decision blocks the build. The detailed behavior below is the implementation
contract for Tara.

## Terms and invariants

- **`sync_id`**: a stable UUID for a synchronized entity. Existing integer IDs remain the
  application's relational keys; the sync protocol never depends on a temporary integer ID.
- **`mutation_id`**: a UUID generated once for one phone operation and reused on every retry.
- **`changed_at`**: when the user pressed Save on that client. This is the conflict clock.
- **`recorded_at`**: when PostgreSQL received the operation. This is for diagnosis and audit,
  never for deciding which user value wins.
- **field clock**: the winning `(changed_at, device_id, mutation_id)` tuple for one editable
  field. The latter two values are deterministic tie-breakers when timestamps are identical.
- **change sequence**: a server-assigned increasing integer used only as the pull cursor.
- **provisional change**: a phone mutation held for review because its target was deleted or
  merged. It is acknowledged to the phone but not applied.

The following invariants must hold:

1. Replaying a mutation produces the same response and no additional record or activity.
2. A sync cursor advances only after the corresponding local SQLite transaction commits.
3. An outbox entry is removed only after the server acknowledges that exact `mutation_id`.
4. A pull never overwrites an unsent local overlay in the UI.
5. A newer edit to field A cannot erase a concurrent edit to field B.
6. A tombstone is synchronized before local data is forgotten.
7. Workspace, user and server environment are part of every local and server sync boundary.
8. One foreground sync worker is the only writer that sends or applies remote changes.

## Architecture

```text
phone screens
    │ read local projections; write local patch + outbox atomically
    ▼
encrypted SQLite ── outbox ──▶ single sync worker ──▶ /api/sync/push
    ▲                                     │                 │
    │                                     │                 ▼
    └──── canonical changes ◀── /api/sync/changes ◀── PostgreSQL
                                      ▲
                                      │ change sequence + field clocks
web, MCP and agents ──────────────────┘
```

The current REST endpoints remain available. The new endpoints are additive, so the
installed app continues working while the server phases are deployed.

## Server data model

Use migration `099_mobile_sync.sql` if 099 is still the next free number when work starts.
All new tables need explicit workspace row-level security; migration 079 only applied its
loop to tables that existed at that time.

### Stable entity identities

Add `sync_id UUID NOT NULL DEFAULT gen_random_uuid()` with a unique index to:

- `contacts` (organizations)
- `people`
- `deals`
- `interactions` (organization activities)
- `people_interactions` (person notes)

Backfill is automatic through the default. Keep existing integer primary and foreign keys.
API projections expose both IDs during the transition; sync requests use `sync_id`.

### `mobile_sync_devices`

One row per installation and signed-in account:

| Column | Purpose |
|---|---|
| `device_id UUID` | Stable random identifier kept in SecureStore. |
| `workspace_id`, `user_id` | Ownership and RLS boundary. |
| `server_environment` | Production or reviewer; prevents cross-environment reuse. |
| `registered_at`, `last_seen_at`, `revoked_at` | Lifecycle and revocation. |
| `app_version`, `schema_version` | Compatibility diagnosis. |

Registration requires the existing JWT. Revoking a device prevents future pushes but does
not erase server records it already created.

### `sync_entity_changes`

An append-only, payload-free change index:

| Column | Purpose |
|---|---|
| `sequence BIGSERIAL` | Pull cursor. |
| `workspace_id` | Tenant boundary. |
| `entity_kind` | Closed enum: organization, person, deal, organization_activity, person_note. |
| `entity_sync_id UUID` | Stable identity. |
| `operation` | `upsert`, `soft_delete`, `hard_erase` or `merge_redirect`. |
| `changed_at`, `recorded_at` | User clock and server receipt clock. |
| `mutation_id`, `device_id` | Nullable for web, MCP and agent writes. |
| `actor`, `correlation_id` | Traceability into the existing audit system. |

Do not store entity payloads here. Pull resolves the current canonical projection inside a
database transaction. This keeps the change index small and avoids retaining deleted personal
data in a second history table.

Keep this metadata indefinitely initially. If pruning is ever needed, clients older than the
oldest retained sequence must receive `bootstrap_required` instead of a partial history.

### `sync_field_versions`

One row per synchronized scalar field:

| Column | Purpose |
|---|---|
| `workspace_id`, `entity_kind`, `entity_sync_id`, `field_name` | Composite primary key. |
| `changed_at` | Winning user edit time. |
| `device_id`, `mutation_id` | Deterministic tie-breaker and provenance. |
| `source` | `mobile`, `web`, `mcp`, `agent` or `migration`. |

This table stores clocks, not field values. Values remain in their domain tables.

For ordinary web requests, MCP calls and agents, `changed_at` is the server transaction time.
For a mobile push it is the validated client time. Existing `updated_at` columns keep their
current meaning—when the server row changed—and must not be reused as field clocks.

### `sync_mutations`

This is the idempotency ledger. `mutation_id` is unique within workspace and device. Store
the request hash, entity identity, status, winning/ignored field names, server IDs and audit
metadata, but not a second copy of the submitted values. A repeated request with the same ID
and same hash returns the recorded outcome. Reusing an ID with different content returns 409.

Statuses are `applied`, `partially_applied`, `ignored_older`, `provisional`,
`rejected_validation` and `rejected_clock`.

### `provisional_mobile_changes`

| Column | Purpose |
|---|---|
| `id`, `workspace_id`, `user_id`, `device_id`, `mutation_id` | Identity and ownership. |
| `entity_kind`, `entity_sync_id` | Missing, deleted or merged target. |
| `reason` | `soft_deleted` or `merged`. GDPR erasure is never stored here. |
| `patch JSONB`, `changed_at`, `recorded_at` | Proposed values and both clocks. |
| `merge_target_sync_id` | Surviving person when applicable. |
| `expires_at` | Exactly 30 days after `recorded_at`. |
| `status`, `reviewed_at`, `reviewed_by`, `decision` | Pending, applied, recreated, discarded or expired. |

The expiry job deletes `patch` contents at 30 days and retains only non-personal audit
metadata. It writes one audit event with the number expired.

### Erasure and merge markers

Hard erasure currently removes rows. Before removal, retain a minimal marker containing only
workspace, entity kind, `sync_id`, operation and time. It contains no name, contact details,
notes or previous values. This lets an offline device learn that it must purge the record.

`people_merge.merge_people` must record a redirect from the removed person's `sync_id` to the
survivor's `sync_id` before the duplicate row is deleted. A pending phone edit to the removed
person becomes provisional; it is never applied to the survivor automatically.

## Capturing every server-side change

The sync log is useful only if web, mobile, MCP and agent writes all enter it. Add PostgreSQL
triggers for the five synchronized tables as the final safety boundary.

The trigger must:

1. Compare `OLD` and `NEW` and ignore bookkeeping columns such as `updated_at`.
2. Update field clocks for fields that actually changed.
3. Append one `sync_entity_changes` row.
4. Use transaction-local sync context when the mobile push service sets it.
5. Otherwise use the server transaction time and the actor/correlation information already
   carried by `gcrm.audit_context`.
6. Record soft deletes, hard erasures and restores explicitly.

Extend the database transaction setup to set transaction-local values for actor, actor type,
correlation ID and, only inside a validated mobile push, device ID, mutation ID and
`changed_at`. Values must reset automatically at transaction end; never keep them as
connection-global state in the pool.

The mobile push service compares incoming field clocks before issuing an update. It includes
only winning fields in the SQL update. The trigger then records precisely those changes. A
normal direct web or agent update still passes through the trigger, which prevents a missed
router from silently bypassing synchronization.

## Sync API

Create `gcrm/api/routers/api_sync.py`, Pydantic boundary models in
`gcrm/sync/contracts.py`, pure ordering/reconciliation functions in
`gcrm/sync/conflict_resolution.py` and database operations in focused `gcrm/tools/db_sync_*.py`
modules. Do not put the protocol into the existing general API module.

### Register device

`POST /api/sync/devices`

The client sends its installation UUID, app version and local schema version. The response
contains the supported protocol version and whether bootstrap is required.

### Bootstrap

`GET /api/sync/bootstrap?token=<opaque>&limit=500`

The first response captures a server high-water sequence. Pages use keyset pagination, never
offset pagination. Return every active organization and person, their active deals, and
non-deleted activity/note history. Exclude sales, subscriptions, images, audio and unrelated
administrative data.

The opaque token contains the high-water sequence and page positions. It is signed, scoped to
the workspace/user/device and expires after 24 hours. Creating or deleting rows while
bootstrap is running is safe: after the last page, the client pulls from the captured
high-water sequence, so anything missed or repeated is reconciled idempotently.

Return typed entity envelopes:

```json
{
  "entity_kind": "person",
  "sync_id": "uuid",
  "server_id": 123,
  "fields": { "name": "...", "pipeline_stage": "prospect" },
  "field_versions": { "name": "2026-11-23T10:00:00Z" }
}
```

Do not return raw database rows or fields outside the mobile contract.

### Push

`POST /api/sync/push`

Accept at most 100 mutations per request. One mutation has:

```json
{
  "mutation_id": "uuid",
  "device_id": "uuid",
  "entity_kind": "organization",
  "entity_sync_id": "uuid",
  "operation": "update",
  "changed_at": "2026-11-23T10:15:00Z",
  "patch": { "phone": "+49...", "pipeline_stage": "prospect" }
}
```

Parse the patch against an allowlist for that entity and operation. Reject unknown fields.
Use the existing business validators for stages, statuses, links and note content. One bad
mutation receives its own error and does not roll back unrelated mutations in the batch.
Each mutation itself is one database transaction.

For each field compare:

```text
(incoming changed_at, incoming device_id, incoming mutation_id)
    >
(stored changed_at, stored device_id, stored mutation_id)
```

Only winning fields are applied. Return an outcome per field and the canonical entity after
the transaction. If the mutation creates an entity, return its integer server ID mapping.

Accept timestamps no more than five minutes ahead of server time. Return `rejected_clock`
with a user-readable instruction to enable automatic date and time. Do not rewrite the
timestamp. Old timestamps are valid because the edit may have been offline for months.

### Pull

`GET /api/sync/changes?after=<sequence>&limit=500`

Return ordered change envelopes, the next cursor and `has_more`. Upserts contain the current
canonical projection and field clocks. Deletions contain only kind, `sync_id`, deletion kind
and time. Resolve rows and capture the page high-water mark in one database transaction so
the cursor and projections agree.

### Review queue API and web screen

Add an admin-only web page at `/offline-changes/`, linked from the web navigation with a
pending count. Each item shows:

- the deleted or merged target and reason;
- phone, edit time, arrival time and proposed field changes;
- expiry date and days remaining;
- merge survivor, when relevant.

Actions are CSRF-protected, transactional and audited:

- **Restore and apply**: only for an ordinary soft deletion. Restore, then apply the proposed
  fields through the same field-clock service.
- **Recreate as new**: create a new organization or person with a new `sync_id`, preserving the
  provisional source in audit metadata.
- **Apply to merged person**: explicitly apply selected fields to the merge survivor.
- **Discard**: purge the patch immediately.

There is no restore action for an erased record. There should not even be a provisional row
for one.

## Conflict examples that define the behavior

### Same field, web edit is newer

```text
10:00 phone saves telephone number while offline
10:15 web saves a different telephone number
12:00 phone reconnects
result: the 10:15 web telephone number remains
```

The phone receives `ignored_older` for that field and then pulls the canonical record.

### Same field, offline phone edit is newer

```text
10:00 web saves telephone number
10:15 phone saves a different telephone number while offline
12:00 phone reconnects
result: the 10:15 phone telephone number wins
```

Arrival at 12:00 does not become the edit time.

### Different fields

```text
10:00 phone edits telephone number
10:15 web edits notes
result: both edits survive
```

### Deleted target

```text
10:00 web soft-deletes person
10:15 offline phone edits person's title
12:00 phone reconnects
result: person stays deleted; title edit enters the 30-day review queue
```

### GDPR erasure

```text
10:00 organization is permanently erased
10:15 offline phone edits it
12:00 phone reconnects
result: server discards the patch; phone purges the organization and related local data
```

Privacy erasure overrides last-edit-wins.

## Android local database

Install the Expo SDK 56 compatible versions of `expo-sqlite` and `expo-network`; do not pick
versions by hand. Use `npx expo install`. Relevant versioned documentation:

- <https://docs.expo.dev/versions/v56.0.0/sdk/sqlite/>
- <https://docs.expo.dev/versions/v56.0.0/sdk/network/>

Enable SQLCipher through the `expo-sqlite` config plugin. SQLCipher is not supported in Expo
Go, so verification uses the existing native Android/EAS build. Generate a random database
key per account/environment and store it in SecureStore. Exclude the database and key from
Android cloud backup.

### Local tables

Use typed tables for fields the phone searches, filters, sorts or edits:

- `local_organizations`
- `local_people`
- `local_deals`
- `local_organization_activities`
- `local_person_notes`
- `sync_outbox`
- `sync_state`
- `bootstrap_generations`

Every entity row contains `sync_id`, nullable `server_id`, canonical server fields,
`server_field_versions`, `bootstrap_generation` and whether it exists only locally. Do not
create a mutable `local_contacts` table. Implement the Contacts list as a repository query or
SQLite view over organizations and people, with deal stage chips and last-contact data joined
from their canonical tables.

Use FTS5 indexes for organization/person name, city, company, email, phone and notes. Keep the
same filter and sort vocabulary as the current server APIs.

### Canonical state plus local overlay

Do not overwrite canonical server fields when a user edits offline. In one SQLite transaction:

1. Insert or update the outbox patch.
2. Record the operation's `changed_at` and `mutation_id`.
3. Notify the repository query.

Repository reads overlay pending patches on canonical rows. Therefore a pull can safely update
the canonical base while an unsent phone value remains visible. When push acknowledges the
mutation, apply the returned canonical entity and remove that exact outbox row in one SQLite
transaction.

For a locally created organization or person, insert a local-only row keyed by `sync_id` and
an outbox create. When acknowledged, attach the returned integer ID without replacing the
`sync_id`; dependent local notes and the initial deal already refer to the UUID.

### Bootstrap generations

Never expose half a bootstrap. Download pages into a new generation while the previous
generation remains readable. After every page and its continuation token is durable, mark the
new generation active in one transaction and remove the old generation. If the process dies,
resume the incomplete generation or discard it; do not clear the working cache first.

### Sync worker

Implement one single-flight foreground worker. Trigger it:

- after login and bootstrap;
- when the app starts or returns to the foreground;
- when `expo-network` reports restored reachability;
- after an online local save;
- when the user selects **Sync now**.

One cycle:

1. Register/refresh the device record if needed.
2. Push outbox mutations oldest first in batches.
3. Apply acknowledgements transactionally and mark provisional items as needing web review.
4. Pull pages until caught up.
5. Apply each page and its cursor in one SQLite transaction.
6. Publish last-success time and counts to the UI.

Use exponential backoff with jitter. A validation failure marks only that mutation; it does
not block later independent mutations. A 401 locks synchronization pending reauthentication
without deleting encrypted local data or the outbox.

Do not add periodic Android background synchronization in the first release. Foreground,
reconnect and save triggers cover the intended use without another background-service and
battery-policy surface.

## Mobile repository and UI changes

Introduce repository interfaces between screens and storage. Screens must not decide whether
data came from HTTP or SQLite.

Suggested modules:

- `engcrm-mobile/services/local-database.ts`: open, key and migrate the encrypted database.
- `engcrm-mobile/services/local-schema.ts`: ordered SQLite migrations only.
- `engcrm-mobile/services/contact-repository.ts`: organizations, people and combined contacts.
- `engcrm-mobile/services/activity-repository.ts`: organization activities and person notes.
- `engcrm-mobile/services/sync-outbox.ts`: atomic mutation enqueue/acknowledgement.
- `engcrm-mobile/services/sync-worker.ts`: the single network synchronizer.
- `engcrm-mobile/services/sync-contracts.ts`: parse server envelopes at the boundary.
- `engcrm-mobile/services/sync-status.ts`: observable pending/error/last-success state.

Replace `usePagedList` network fetching incrementally. Local lists can still expose pages to
the screens, but pagination is a SQLite query and never a prerequisite for first paint.

Add a compact status area in the drawer or Settings:

- **Up to date · synced 2 minutes ago**
- **Offline · 4 changes waiting**
- **Syncing 2 of 7**
- **1 change needs review on the web**
- **Could not sync** with the specific validation or clock problem
- **Sync now**

Rows with pending overlays get a small pending icon. Provisional rows get **Review on web**;
they do not remain in the outbox and are not retried.

## Authentication, logout and account isolation

The cache key is `(server environment, workspace, user)`. Production and reviewer data can
never share a database. Validate the signed-in identity before opening a cache.

On explicit logout:

1. Attempt a final sync when pending mutations exist.
2. If offline or unsuccessful, explain how many changes exist only on the phone.
3. Offer **Stay signed in** or a separately confirmed **Discard changes and log out**.
4. After a safe logout, close and delete the SQLite database, delete its SecureStore key,
   stop field mode and clear the existing specialized queues belonging to that account.

Token expiry is not explicit logout. Lock the UI, retain the encrypted database and resume
after the same account reauthenticates. Signing into a different account requires clearing the
previous cache through the same guarded flow.

## Audit and diagnostics

Use one correlation ID for a sync cycle and a child correlation suffix per mutation. Echo the
existing `X-Request-ID` through all sync responses. Every applied, ignored, provisional,
reviewed, expired or rejected mutation writes an append-only audit record with the real actor.

Expose diagnostics in Settings without exposing record values:

- device ID suffix and app/schema/protocol versions;
- last bootstrap and successful sync times;
- current server cursor;
- pending, failed and provisional counts;
- last correlation ID and error category;
- **Reset local cache** only when the outbox is empty.

Log metrics for bootstrap duration and size, push/pull counts, retry count, oldest pending age,
ignored fields, provisional changes and cursor lag. Never log names, notes, email, phone or
patch JSON.

## Test-first build order

Every phase starts with failing behavior tests. Never weaken an existing test to accommodate
the sync layer.

### Pure unit tests

- Field comparator: older, newer and exact-timestamp tie cases.
- Separate fields merge without loss.
- Operation/patch allowlists reject unknown or web-only fields.
- Clock validation rejects future timestamps and accepts old offline timestamps.
- Bootstrap and pull envelope parsing rejects illegal entity states.
- Local overlay preserves pending values over a newer canonical pull until push resolves it.
- Backoff and single-flight worker behavior.

Run mutation testing on the Python and TypeScript field-comparison code. Every inverted
comparison and removed tie-breaker must be killed.

### Real PostgreSQL integration tests

- Migration and rollback-safe additive schema on the real engine.
- RLS prevents cross-workspace device, cursor, mutation and provisional access.
- Web, MCP, agent and direct domain-service writes all create sync changes.
- A repeated mutation creates one organization/person/activity only.
- Crash after server commit but before response is safe to retry.
- Mixed winning/losing fields update only the winners.
- Soft delete creates a tombstone and later phone edit becomes provisional.
- Merge redirect creates a provisional item targeting the survivor.
- GDPR erasure emits a minimal purge marker and stores no provisional values.
- Thirty-day expiry purges provisional JSON.
- Pull cursor is ordered, stable and cannot skip a concurrent change.

### Mobile integration tests

- SQLite migrations from empty and from each released local schema version.
- Interrupted bootstrap keeps the previous generation visible.
- Atomic local save creates both overlay and outbox entry.
- Atomic acknowledgement updates canonical state, cursor and outbox.
- App termination at every transaction boundary recovers without duplication or loss.
- Production/reviewer and two user accounts cannot read each other's cache.
- Explicit logout guards pending changes and wipes database plus key after confirmation.
- Contacts, Organizations and People filters/sorts/stage badges match current behavior locally.

### End-to-end scenarios

Automate the conflict examples above against real PostgreSQL and the mobile repository. Add
an Android flow test for:

1. bootstrap while online;
2. disable connectivity;
3. create an organization and person and add an activity;
4. restart the app and see all three locally;
5. restore connectivity;
6. see one copy on the server and an empty outbox;
7. edit the same field on web and phone with controlled timestamps and verify the winner;
8. delete on web, edit on phone, and review the provisional change on web.

The web review screen also needs Playwright coverage for keyboard operation, CSRF, all actions
and the 30-day expiry display.

## Delivery phases

### Phase 1 — server foundation, no mobile behavior change

1. Add stable UUIDs and sync metadata tables with RLS.
2. Add field comparator and mutation ledger tests.
3. Add universal change-capture triggers and prove existing web/MCP/agent writes appear.
4. Add device registration, bootstrap and pull endpoints.
5. Add push for updates but keep it disabled outside tests.

Deploy this first. Verify audit, cursor monotonicity, payload size and production query plans.

### Phase 2 — encrypted read-only mobile database

1. Add Expo SQLite/Network dependencies and SQLCipher native configuration.
2. Add local migrations, bootstrap generations and repositories.
3. Switch Organizations, People, Contacts and details to local reads behind a feature flag.
4. Keep writes online through existing endpoints while verifying that server changes appear
   locally after pull.
5. Measure bootstrap size and warm-list first paint on Chris's Android phone.

Acceptance gate: after one bootstrap, kill connectivity and restart the app; every active list
and cached detail/history remains readable, searchable, filterable and correctly staged.

### Phase 3 — ordinary offline writes

1. Add local overlay/outbox and single sync worker.
2. Enable ordinary field and existing-deal edits.
3. Enable offline organization/person creation with initial offer/deal.
4. Enable offline organization activities and person notes.
5. Add pending/status/error UI and guarded logout.

Acceptance gate: the offline create/restart/reconnect end-to-end scenario passes without a
duplicate, lost field or false “synced” indication.

### Phase 4 — deleted and merged target review

1. Add provisional table and 30-day purge job.
2. Add merge redirects and erasure-safe purge markers.
3. Add the web review screen and audited actions.
4. Add phone status for provisional and expired mutations.

Acceptance gate: deletion never auto-restores; an ordinary deleted-target edit is reviewable
for 30 days; GDPR-erased data is not retained.

### Phase 5 — controlled rollout

1. Enable for the reviewer environment and a disposable account first.
2. Run clock-skew, interrupted-network, process-kill and large-bootstrap tests.
3. Enable read-only production cache for Chris.
4. Enable production offline writes after at least several normal sync cycles.
5. Keep telemetry and a diagnostic reset path during the first mobile release.

Do not disable synchronization while an outbox is non-empty. A kill switch may stop new
offline edits, but it must continue draining already accepted local mutations.

## Acceptance criteria

The project is complete only when all of the following are demonstrated:

- Lists render from encrypted local storage without a network request blocking first paint.
- Every active organization, person and relevant deal is present after bootstrap.
- Contacts is derived locally and matches the server's combined list semantics.
- Ordinary offline create/edit/activity flows survive app restart and synchronize later.
- Replaying any mutation creates no duplicate and changes no outcome.
- Same-field conflicts follow `changed_at`; different-field edits both survive.
- The UI never labels an outbox mutation “synced” before server acknowledgement.
- Soft-deleted targets stay deleted and produce a 30-day provisional review item.
- GDPR erasure purges local data and retains no proposed personal values on the server.
- Workspace, user, production and reviewer caches are isolated.
- Web/MCP/agent changes reach the phone through the same cursor protocol.
- Correlation IDs and append-only audit records trace every state change and review decision.
- Unit, real-PostgreSQL integration, mobile integration, web/Android end-to-end, lint,
  typecheck and dependency scans are green.

## Explicitly later

- Offline deletion or duplicate merging.
- Offline creation/removal of additional deals after initial contact creation.
- Offline sales, contracts or subscription changes.
- Binary card images, audio and documents in the general sync database.
- Periodic Android background synchronization while the app stays closed.
- Multi-user collaborative presence or live keystroke synchronization.
- Replacing the existing specialized card-capture and field-location queues; they can migrate
  to the general outbox only after the core protocol is proven.
