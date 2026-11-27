# Follow-ups screen

Date: 2026-11-24 · Status: implemented locally; awaiting push

## Purpose and scope

Add a Follow-ups screen to the web app so Chris can see and manage outstanding
commitments and planned check-ins across organizations, people and offers.
Chris authorized implementation on 2026-11-24; pushing and deployment still
require his separate instruction.

## Agreed behavior

| Decision | Behavior |
| --- | --- |
| Navigation | Follow-ups has its own entry in the web navigation. |
| One row | One outstanding follow-up, with its own identity and completion. |
| Multiple tasks | A company can have several follow-ups for the same offer, including tasks involving different decision makers. |
| Date order | Oldest first by default; switch to Newest first. Both directions include overdue and future dates. |
| No date | Actual follow-ups without a date form a clearly labeled group at the bottom in either direction. |
| Names | Company and person names link to their existing records. Show both where a named person belongs to the company. |
| Sales context | Show the relevant offer, its sales stage and its status. Keep task type separate from these sales fields. |
| Offer scope | All offers by default; allow filtering to an offer. General promises without an offer remain visible in the default view. |
| Text | Display the follow-up text directly in the row. |
| Finding tasks | Search company, person and follow-up text; filter by date range, sales stage, offer and follow-up type. |
| Working from the list | Edit the follow-up, change its date and mark it done without leaving the screen. |
| Sources | Include deal next steps and promises recorded in activities, with each task appearing once. |
| Older promises | Review older activity promises before putting them in the active list. |

## Commitment and Check-in

**Commitment** means somebody is expecting an action from us: sending a proposal,
answering a question or providing promised technical details.

**Check-in** means we deliberately plan to reconnect: asking how a project is
progressing or returning to a training discussion next month.

Both types share the same date ordering and have visible labels. The type filter
can show either type or both. One row might say “Call purchasing about approval”
and another “Send engineering the specification,” even for the same company and
offer. Each can have a different date and contact person.

Being contacted does not automatically create a task. A sales stage, elapsed
time since contact or a missing reply does not automatically create one either.
Only an explicit commitment or planned check-in belongs here; initial outreach
to an uncontacted candidate does not.

A Candidate can still have a real follow-up. If that person is expecting our
reply, the task belongs on this screen even if their sales stage is unchanged.
Contacting a second decision maker belongs here when it is a concrete next step
in an existing relationship. Do not impose a blanket Candidate exclusion or
require a particular `contacted` status.

## List and task lifecycle

The main columns are Follow-up date, Company or person, Type, Offer, Sales stage,
Status, Follow-up and Actions. Make the task text readable without a tooltip.
Use the existing stage badges and date presentation. Mark overdue tasks and
today's tasks with text as well as color.

The dated portion sorts by calendar date, with a stable secondary order for
equal dates. Undated tasks always follow every dated task, including when dates
are descending. Search and filters apply before sorting and pagination; page
boundaries must not move undated tasks ahead of dated matches. A date-range
filter applies to dated tasks; keep matching undated tasks in their bottom group
and make that behavior visible beside the filter.

Completing a task removes it from the active list and preserves its history.
Logging an email, call or meeting does not automatically complete a task or its
siblings. Editing a task's text or date changes that task, not the others for the
same offer. Changing sales stage does not silently complete outstanding promises.

Recommended implementation details: create tasks from this screen and existing
record screens; require nonblank text and a choice of Commitment or Check-in;
make dates optional. Keep the sales stage/status read-only here, with links to
the existing deal controls. Provide a way to dismiss an obsolete task without
calling it completed; retain that distinction in history. Initial outreach found
during review stays outside the active follow-up list without deleting its
original next step.

## Existing code and storage

The current implementation has two distinct sources:

- `deals.next_step` and `deals.next_step_date` hold one current task per deal.
  Stage, status, offer and the optional company contact person also live on the
  deal. `gcrm/tools/deal_records.py` writes changes and completion entries to
  organization or person activity history. The current blank-text operation
  treats clearing a next step as completion.
- Organization activities store promises in `interactions.next_action` and
  `interactions.next_action_date`. `gcrm/tools/db_interactions.py` writes these
  through `log_meeting_note`; voice capture can also write these fields. These
  promises have no independent completion tracking.

The Contacts feed is not a suitable source for the complete task list.
`gcrm/tools/db_contact_feed_query.py` picks the earliest dated deal next step
per owner and groups company-linked people under their company. Follow-ups must
retain every eligible task and its specific person and offer.

## Proposed implementation approach

Introduce a canonical collection of follow-ups instead of extending the single
next-step text field to encode several tasks. Each task needs:

- Stable identity, workspace and organization/person target, with an optional
  named contact person and optional deal/offer association.
- Commitment or Check-in, text, optional due date, active/completed/dismissed
  lifecycle, and completion/dismissal timestamps where applicable.
- Source identity for imports and activity-linked tasks, plus review state for
  historical entries whose relevance or type has not been confirmed.
- Creation/update timestamps and the existing actor/correlation audit context.

For a deal-associated task, show that deal's current stage and status. For a
general promise, label the offer General and show no invented stage/status;
allow association with a real deal during review or editing. Validate that every
target, contact person, source and deal belongs to the same workspace and that
the named person belongs to the intended company.

Route task creation, edits, rescheduling, completion and review through one
shared persistence service. Existing web, mobile, MCP and voice entry paths must
use or adapt to that service so the screen cannot miss newly recorded promises.
Keep existing clients working; do not silently overwrite several tasks with the
legacy single-next-step field. A compatibility response may present the earliest
active task. Chris chose the compatibility behavior on 2026-11-24: older
clients without a task ID edit or complete the earliest active task on the deal
(dated first, then undated, with ID as a stable tie-breaker), never its siblings.
Updated clients should identify the task and detect stale writes.

**Changed on 2026-11-27 (Chris):** nothing edits an existing follow-up's text any
more. A next step from any client (deal card, phone, offline sync, field mode)
adds a follow-up of its own; saving one already there adds nothing, and with a type
it activates a waiting step with the same words instead of copying it. A blank step
still marks the earliest active follow-up done. The deal card lists the active
follow-ups and only adds or marks done; editing happens on the Follow-ups page.
`deals.next_step` shows the earliest active follow-up, also after an activity
promise; with none active it shows the step just saved without a type.
The card's Add and Done are written to the owner's history like a next step, and the
card says how many of the deal's entries wait in Review. Migration 114 brought next
steps that had fallen behind up to date.

Add a Commitment/Check-in choice to activity and voice capture forms. Existing
clients that cannot provide a choice send unclassified promises to review.

Coordinate this work with the separate offline mobile sync plan. The new screen
is web-only; a mobile Follow-ups screen is outside this first delivery. Existing
mobile operations still need safe behavior against the new server model.

## Review and migration

Import existing next steps and historical activity promises using stable source
references, so rerunning the import cannot create duplicate tasks. Preserve the
original activity history and the current record screens during transition.
Do not scrape arbitrary notes for implied promises or use an LLM to decide what
is still owed.

Older activity promises go to Review older follow-ups. Show their source date,
original text, company/person, offer if known and any due date. Chris can keep
one, select Commitment or Check-in, adjust its date or text, dismiss it as no
longer relevant, or link it to an already represented task. Keep reviewed
decisions durable so dismissed promises do not reappear on the next import.

Current deal next steps also need explicit classification if their type is
unknown. Put uncertain tasks through review rather than guessing that all next
steps are Check-ins or that every old promise remains outstanding. Date-only
legacy entries need text supplied during review before activation.

A generated `next_step` history entry is evidence of a deal task, not a second
task to import. Match sources by durable identity where available. Similar text
and dates may suggest a duplicate during review, but must not automatically
merge distinct promises to different decision makers. Completion must not revive
a task from its unchanged historical source.

## Integration inventory (implementation preparation)

- Deal next steps: `deal_records.set_deal_next_step` serves the web deal form,
  mobile deal API and field MCP; `people_next_step.set_person_next_step` is a
  separate legacy mobile person API and calls `write_next_step` directly.
  Field MCP undo currently restores the old text and date by deal ID alone.
- Organization activities: `db_interactions.log_meeting_note` serves mobile
  activity capture, the web statistics form, field MCP and the interview
  supervisor. `db.log_voice_interaction`, called by the voice API, writes
  `interactions.next_action` independently and needs the same treatment.
- Deal and next-step summaries are read by the deal panels, People,
  Organizations, Contacts, mobile lists, exports and merge handling. A person
  stage-clear can soft-delete a deal unless its legacy next-step fields are set;
  this protection must account for every outstanding canonical task.
- The separate offline plan allows offline edits to deal next steps and new
  organization activities. Its future mutation format must carry a stable task
  identity and preserve conflict handling when that plan is implemented.

These paths are an inventory, not evidence that the compatibility contract or
workspace isolation has already been implemented or verified.

Implementation: migration 099 snapshots existing sources for review; the shared
task service keeps individual lifecycle states, scopes tasks to a workspace,
and exposes the earliest active task to old next-step clients. New activity and
voice forms offer a type choice; unclassified old-client entries go to review.
Field MCP undo stores the task identity and version. Follow-ups are included in
workspace exports and follow the existing owner-erasure rules. The web worklist
supports review, creation, independent edits, completion and dismissal.

## Delivery and verification

1. Inventory all next-step and activity-promise writers and readers, including
   installed clients and MCP undo. Set the compatibility contract and the schema
   alongside the offline sync work before implementing migrations.
2. Build the task model and shared service, with transactional mutations,
   workspace isolation, retry-safe imports/completion and preserved history.
3. Connect existing capture and next-step entry paths, then implement historical
   review with explicit classifications and duplicate linking.
4. Add the web list, navigation, filters, both date directions, undated group
   and actions using existing authentication, roles and English/German UI text.
5. Verify on real PostgreSQL: several tasks per company/offer; company and person
   targets; commitments on Candidates; exclusion of initial outreach; general
   promises; import retries; review dismissal; source linking; safe legacy writes;
   concurrent edits; and cross-workspace read/write rejection.
6. Cover the main browser flows: search/filter, both sort directions, undated
   tasks after all dated matches across pagination, independent completion,
   editing/rescheduling, review and keyboard access. Check small-screen layout.

Use the repository's coding standards and test-first workflow when building.
Do not weaken existing tests. Commit implementation work locally on main and
wait for Chris's instruction before pushing. No reminders, automatic outreach
or agent follow-up execution are included in this screen.
