# Contact state

A contact carries three independent facts. They used to be one `status` column,
which forced unrelated things to overwrite each other — a bounced address erased
a booked meeting, an opt-out erased a hard-won pipeline position. Since
migration `041` they are three:

| Axis             | Column                                                     | Changes                      |
| ---------------- | ---------------------------------------------------------- | ---------------------------- |
| Pipeline stage   | `pipeline_stage`                                            | Moves forward, one at a time |
| Current status   | `status`                                                    | Often, and can go sideways   |
| Suppression      | `do_not_contact`, `email_bounced`, `research_exhausted`     | Independently of both        |

The canonical lists live in [`gcrm/contact_state.py`](gcrm/contact_state.py).
The mobile app mirrors them in `engcrm-mobile/services/contactState.ts`, and
`tests/test_contact_state.py` fails if the two copies ever disagree. Nothing
else defines a status list.

## Pipeline stage — where the relationship stands

| Stage             | Meaning                                                       |
| ----------------- | ------------------------------------------------------------- |
| `candidate`       | Found by research, not yet evaluated                          |
| `suspect`         | Looks like a fit; we have reached out or are about to         |
| `prospect`        | They engaged — a real conversation exists                     |
| `opportunity`     | Concrete deal in motion                                       |
| `customer`        | Closed; working together                                      |
| `not_in_pipeline` | No fit, declined, or never going anywhere                     |

## Status — what is happening right now

| Status      | Meaning                                                        |
| ----------- | -------------------------------------------------------------- |
| `none`      | Nothing is going on                                            |
| `ready`     | Scored a fit, first outreach not yet sent                      |
| `contacted` | Outreach sent, waiting for a reply                             |
| `meeting`   | Meeting or discovery call arranged                             |
| `proposal`  | Proposal or quote sent, awaiting decision                      |
| `dormant`   | Was active, gone quiet past the dormancy threshold (12 months) |
| `on_hold`   | Parked on purpose — timing or budget                           |
| `dropped`   | Not being pursued                                              |

`ready` is what used to be called `cold`. The old name meant the opposite of
what it said: not an untouched cold lead, but the readiest state there was.

## Suppression flags — true regardless of stage or status

| Flag                 | Set by                                | Effect                                     |
| -------------------- | ------------------------------------- | ------------------------------------------ |
| `do_not_contact`     | The opt-out/consent flow              | Blocked from all outreach; GDPR enforcement |
| `email_bounced`      | Bounce handling in the inbox agent    | Excluded from outreach until re-verified    |
| `research_exhausted` | Research/enrichment finding nothing   | Skipped by enrichment; still workable by hand |

A flag never replaces a stage or a status. An organization can be at
`opportunity` / `meeting` **and** have a bounced address — that is the case the
old single column could not express.

## Typical combinations

Advisory, not enforced. `gcrm/contact_state.py` lists which statuses normally
accompany each stage; the data-quality audit reports pairs outside that list,
and unusual pairs are logged but always written.

| Stage             | Usual statuses                            |
| ----------------- | ----------------------------------------- |
| `candidate`       | `none`, `ready`                           |
| `suspect`         | `ready`, `contacted`, `dormant`, `on_hold` |
| `prospect`        | `contacted`, `dormant`, `on_hold`         |
| `opportunity`     | `meeting`, `proposal`, `dormant`, `on_hold` |
| `customer`        | `none`, `dormant`, `on_hold`              |
| `not_in_pipeline` | `dropped`, `none`                         |

## Who writes what

- **Research agent** — saves new rows as `candidate` / `none`, raising
  `research_exhausted` when the business has no web presence at all.
- **Scout agent** — judges fit, then writes both axes: a fit becomes
  `suspect` / `ready`, an unclear verdict stays `candidate` / `none` with the
  reasoning in the notes for a human to look at, and no fit becomes
  `not_in_pipeline` / `dropped`.
- **Enrichment agent** — writes contact details only; raises
  `research_exhausted` when it finds nothing.
- **Outreach / approvals** — first send moves `ready` → `contacted`.
- **Inbox agent** — raises `email_bounced` on a bounce, `do_not_contact` on an
  opt-out. Neither touches the pipeline.
- **You** — every stage and status is editable on the contact detail page, on
  the interview CLI, and through the MCP tools.

## Validation

There is no CHECK constraint on either column. Migration `026` records what
happened the last time the database rejected values the agents legitimately
write while their stderr went to `/dev/null`: scans silently reported "0 new
contacts saved" for weeks. `coerce_stage()` and `coerce_status()` do the job in
the application instead — an unknown value falls back to the default and is
logged, so a bad write is visible without ever costing a row.

## Retired vocabulary

Migration `041` mapped the old values onto the new axes:

| Old status                                   | Became                                 |
| -------------------------------------------- | -------------------------------------- |
| `candidate`, `maybe`, `lead_unverified`      | `candidate` / `none`                   |
| `cold`                                       | `suspect` / `ready`                    |
| `contacted`                                  | `suspect` / `contacted`                |
| `networking_visit`                           | `prospect` / `on_hold`                 |
| `dormant`, `on_hold`                         | `prospect` / same status               |
| `meeting`, `proposal`                        | `opportunity` / same status            |
| `accepted`                                   | `customer` / `none`                    |
| `dropped`, `rejected`                        | `not_in_pipeline` / `dropped`          |
| `do_not_contact`, `opt_out`                  | `not_in_pipeline` + `do_not_contact`   |
| `bad_email`                                  | `suspect` + `email_bounced`            |
| `cannot_find_more_data`                      | `candidate` + `research_exhausted`     |

An opt-out recorded in `consent_log` also raises `do_not_contact`, whatever the
status column said — the consent log is the legal record.
