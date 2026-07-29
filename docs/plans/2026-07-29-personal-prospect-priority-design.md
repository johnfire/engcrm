# Personal Prospect Priority Design

**Date:** 2026-07-29  
**Issue:** [#43 — need a way for users to rate potential cold clients, really at every stage](https://github.com/johnfire/engcrm/issues/43)

## Goal

Let every authenticated user independently assign a personal priority from 1 to
5 to any contact, at any pipeline stage:

| Value | Meaning |
| --- | --- |
| 1 | Best / act now |
| 2 | High |
| 3 | Medium |
| 4 | Low |
| 5 | Not important now |

An unrated contact has no priority. A user's priority is visible only to that
user. No team average or other users' priorities are exposed.

This is a human judgment signal. It must remain separate from:

- `contacts.fit_score`, the agent-generated 0–100 suitability score;
- `ai_analysis.priority_score`, the agent-generated outreach urgency;
- `contacts.rating`, the public Google venue rating; and
- `contacts.starred`, the shared yes/no favourite marker.

## Data Model

Add a `contact_user_priorities` table:

```sql
CREATE TABLE contact_user_priorities (
    id SERIAL PRIMARY KEY,
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    contact_id INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    priority SMALLINT NOT NULL CHECK (priority BETWEEN 1 AND 5),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, contact_id)
);
```

Add indexes for `(user_id, priority)` and `(contact_id)`. The write path must
verify that the user and contact belong to the same workspace. `workspace_id`
is stored explicitly to support safe workspace-scoped queries and future row
level security.

Setting a priority uses an upsert. Clearing it deletes the user's row. Contact
and user deletion cascade to remove orphaned priorities.

## Authorization and Privacy

Both admins and spectators may read, set, change, and clear their own priority.
Spectators remain unable to edit shared contact fields or run admin-only
actions.

The server derives `user_id` and `workspace_id` from the authenticated web
session or mobile JWT. Clients never submit a user identifier. Reads return
only the current user's priority, and writes cannot address another user's row.

The transitional shared break-glass admin has no user ID and therefore cannot
own a personal priority. Contact reads under that identity return an unrated
value, and priority writes return `403 Personal account required`. This avoids
creating a misleading shared "personal" identity.

Priority changes are recorded in the audit log with an action such as
`contact.personal_priority_changed`, a `contact:<id>` resource, and a result
that records the transition without including another user's data.

## Server and API

Create a small persistence module responsible for:

- retrieving priorities for a page of contact IDs for one user;
- retrieving one user's priority for one contact;
- upserting a value from 1 to 5;
- clearing a value; and
- enforcing user/contact workspace membership.

Web contact queries left-join the current user's priority so lists can filter
and sort without per-row database calls.

Add an authenticated endpoint:

```http
PUT /api/contacts/{contact_id}/personal-priority
Content-Type: application/json

{"priority": 1}
```

Sending `{"priority": null}` clears the rating. The endpoint returns:

```json
{"personal_priority": 1}
```

Expected failures are:

- `400` for values outside 1–5 or malformed input;
- `403` when the transitional shared admin has no personal user identity;
- `404` when the contact is absent or outside the user's workspace; and
- `401` when unauthenticated.

The standard contact list and detail responses gain
`personal_priority: number | null`.

## Web Experience

The contact list gains:

- a `P1`–`P5` badge, or `—` for unrated contacts;
- a Personal priority filter with P1 through P5 and Unrated;
- a Personal priority sort, ascending by default so P1 appears first and
  unrated contacts appear last; and
- preservation of the priority filter in sorting, pagination, clearing, and
  print links.

The contact detail page shows a dedicated Personal priority control near the
shared agent fit score. It uses five labelled buttons:

- `1 Best`
- `2 High`
- `3 Medium`
- `4 Low`
- `5 Not now`

A Clear rating action returns the contact to unrated. Selection saves
immediately through a focused endpoint rather than submitting the admin-only
contact edit form. The control exposes pressed, busy, success, and error states
for keyboard and assistive-technology users. This lets spectators use it
without granting permission to edit shared contact data.

English and German translations describe the field as personal priority, not
an agent score or public rating.

## Android Experience

The `Contact` and `ContactDetail` types gain
`personal_priority: number | null`. Contact rows display the user's `P1`–`P5`
badge separately from the existing fit-score badge.

The contact list adds Personal priority sorting. Filtering includes P1 through
P5 and Unrated without removing the existing status filters.

The detail screen uses the same five labelled choices and Clear rating action
as the web interface. A selection updates optimistically, disables repeated
input while the request is running, and rolls back with a visible retry message
if saving fails. React Native accessibility roles and selected/busy states make
the control usable with TalkBack.

The mobile client calls the focused priority endpoint. It does not gain a
general contact-edit endpoint, preserving the existing separation between
spectator self-service and admin contact management.

## Agent Behaviour

Agents do not read or modify personal priorities in the initial implementation.
Research, enrichment, scout, outreach, opportunity analysis, and follow-up keep
their existing ordering and scoring behaviour.

This prevents a user's judgment from silently influencing an agent decision
and prevents an agent run from overwriting human input. A future feature may
explicitly opt into using personal priority, but that is outside issue #43.

## Validation

### Database and persistence

- Migration applies to a fresh and upgraded database.
- Only priorities 1–5 are accepted.
- Upsert changes only the current user's row.
- Clear removes only the current user's row.
- Cross-workspace reads and writes return no contact.
- User and contact deletion cascade correctly.

### Web

- Admins and spectators can set, replace, and clear their own priority.
- A user never sees another user's priority.
- List filtering, sorting, pagination, and unrated ordering work.
- Contact detail renders all states in English and German.
- Keyboard operation and accessible labels/states are present.

### API and Android

- Authentication and workspace boundaries are enforced.
- The shared break-glass identity cannot create a personal priority.
- Invalid values and missing contacts return the documented errors.
- List/detail serialization returns only the signed-in user's value.
- Android list and detail render rated and unrated contacts.
- Saving, clearing, busy state, rollback, and retry are covered by tests.

### Regression

- Existing agent scores and opportunity analysis remain unchanged.
- Existing starred sorting and status filtering still work.
- Spectators still cannot mutate shared contact fields.

## Out of Scope

- Team averages or rating distributions.
- Viewing or editing another user's priority.
- Agent use of personal priorities.
- Priority history beyond the existing audit record.
- Notifications or automatic outreach driven by personal priority.
