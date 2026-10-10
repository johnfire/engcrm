# Offers and deals: one CRM, several things to sell

Date: 2026-10-10 · Status: designed, not started

## Why

Until now the CRM has sold one thing: AI consulting. Every organization and every person
carries a single pipeline stage and status, and that stage silently means "where we stand on
consulting".

Christopher now also sells three apps directly to businesses: **LearnWohl** (language
learning, e.g. for language schools), **LeGuild.art** (e.g. for small galleries) and
**notes-world**. He expects 100–300 contacts per app in the next six months. Most of them
will be pitched one thing, and some will be pitched two.

One stage per contact cannot hold that. Jamie Simmons (Simmons Language School) can be a
LearnWohl *prospect* and not in the consulting pipeline at all. A gallery can be a
LeGuild.art *customer* and a consulting *suspect*. With one column, moving someone along for
one product overwrites where they stand on another. This is the collision migration 041
fixed when one status column held three facts.

The fix is the usual CRM split: the **contact** (organization or person) is separate from
the **deal** (one offer, one stage, one next step). One contact can have several deals.

## Decisions (agreed with Christopher, 2026-10-10)

| Question | Decision |
|---|---|
| Where per-product tracking lives | A pipeline per offer: a deal per contact per offer, with its own stage, status and next step. Separate workspaces were ruled out: a workspace is a tenant, and splitting would duplicate people and their history. |
| Stage vocabulary | The existing stages and statuses (`gcrm/organization_state.py`) for every offer. No offer-specific stages. |
| Paying app customers | Stage `customer`, with a **subscription** on the deal (€/month, start, end). No `subscriber` stage. Revenue is tracked. |
| Who owns a deal | Normally an organization, with an optional contact person. If the person has no organization in the CRM, the person owns the deal. |
| Today's stages | They become **Consulting deals**. Afterwards the deal is the only place a stage lives; consulting is not special-cased. |
| Log entries | Carry an optional offer. It is filled in automatically when the contact has one open deal; otherwise you pick one. "General" (no offer) is allowed. |
| Adding offers | In Settings → Offers. Initial offers: Consulting, LearnWohl, LeGuild.art, notes-world. |
| Billing | The apps have their own billing. Subscriptions are entered by hand now. The design leaves room for a later sync (see "Later"). |
| Agents | App selling is manual for now. The agents stay on consulting. Agents for app leads come later. |
| Privacy | Do whatever is needed to cover it (see "Privacy"). |

## Data model

### `offers`: what is for sale

| Column | Notes |
|---|---|
| `id`, `workspace_id` | Offers are per workspace, like everything else. |
| `slug` | Stable key (`consulting`, `learnwohl`, `leguild`, `notes-world`). Unique per workspace. Code and agents refer to offers by slug, never by name. |
| `name` | Display name, renamable. |
| `website` | Entered in Settings. Used in sign-offs and on the privacy notice. |
| `revenue_kind` | `one_off` or `subscription`. Only decides which revenue button the deal card shows first; both kinds can be recorded on any deal. |
| `sort_order`, `archived_at`, `created_at` | Archived offers are hidden from pickers but keep their deals and history. |

Seeded per workspace: Consulting (`one_off`), LearnWohl, LeGuild.art and notes-world
(`subscription`). An offer cannot be deleted once it has deals; it can only be archived.

### `deals`: one offer, one contact

| Column | Notes |
|---|---|
| `id`, `workspace_id`, `offer_id` | |
| `contact_id` | The organization (`contacts.id`). Set for organization deals. |
| `person_id` | For an organization deal: the optional contact person. For a person deal: the owner. |
| `pipeline_stage`, `status` | Same vocabulary as today; coerced in the application layer as today. No CHECK constraint, for the reason recorded in migration 041. |
| `next_step`, `next_step_date` | Moved here from `people`. |
| `notes` | Notes about this deal only. General notes stay on the contact. |
| `created_at`, `updated_at`, `deleted_at` | Soft delete, like the rest of the CRM. |

Constraints:

- `CHECK (contact_id IS NOT NULL OR person_id IS NOT NULL)`.
- One live deal per offer per organization: a unique partial index on `(offer_id, contact_id)`
  where `contact_id IS NOT NULL AND deleted_at IS NULL`.
- One live deal per offer per person-owned deal: a unique partial index on
  `(offer_id, person_id)` where `contact_id IS NULL AND deleted_at IS NULL`.

A second consulting project for an existing customer is a second **sale** on the same deal,
not a second deal.

These stay on the contact, because they are about the contact and not about any one offer:
`do_not_contact`, `email_bounced`, `research_exhausted`, `starred`, `flagged`,
`visit_when_nearby`, the person's rating, and how the record was created.

### `subscriptions`: recurring revenue on a deal

| Column | Notes |
|---|---|
| `id`, `workspace_id`, `deal_id` | |
| `amount_eur_month` | `NUMERIC(12,2)`, > 0. |
| `started_on`, `ended_on` | `ended_on` is NULL while running. CHECK `ended_on >= started_on`. |
| `note`, `created_at`, `deleted_at` | |

A price change ends one row and starts another, so past months keep their real amount.

### Changes to existing tables

| Table | Change |
|---|---|
| `sales` | Add `deal_id`. The backfill points every existing sale at its organization's Consulting deal. `contact_id` stays until cleanup (phase 5), then it is dropped: the deal already names the owner. |
| `interactions`, `people_interactions` | Add nullable `offer_id`. NULL means general. Existing rows stay NULL. |
| `approval_queue` | Add `offer_id`. Existing and agent-written drafts are Consulting. Approving a draft logs the interaction with that offer and moves that offer's deal. |
| `stage_changes` | Add `offer_id` and `deal_id`. `entity_type`/`entity_id` keep naming the owner (organization or person), so existing queries still work. The backfill sets every existing row to Consulting. A trigger on `deals` replaces the triggers on `contacts` and `people`. |
| `pipeline_snapshots` | Add `offer_id` to the row and to the primary key. The backfill sets existing rows to Consulting. Snapshots count deals per offer per stage. |

### Migration (backfill)

1. Seed the four offers for every workspace.
2. Every organization gets a Consulting deal with its `pipeline_stage` and `status`. Soft-deleted
   organizations get a soft-deleted deal (same `deleted_at`), so restoring one restores its deal.
3. Every person with a `pipeline_stage` gets a Consulting deal owned by the person, carrying
   their `next_step` and `next_step_date`. A person's stage and their employer's stage are
   separate facts today, and they stay separate deals.
4. A person with a `next_step` but no stage gets a Consulting deal at `candidate`, so no next
   step is lost. The migration report lists these people.
5. Stage history, snapshots, sales and drafts are backfilled as described above.

Every step only fills rows that are not filled yet, so re-running the migration changes
nothing. The old columns (`contacts.pipeline_stage`, `contacts.status`,
`people.pipeline_stage`, `people.next_step`, `people.next_step_date`) are no longer read or
written after phase 1. They are dropped in phase 5.

## Screens (web and mobile)

1. **Organization and person pages: Deals panel.** One card per deal: offer, stage, status,
   next step, contact person, and revenue (the one-off total, or "€X/month since <date>").
   Stage and status save on tap. Buttons: **+ Add deal** (pick an offer), **Start / End
   subscription**, **Record sale**. This replaces the stage and status controls at the top of
   these pages. A person page also shows deals of their organization in which they are the
   contact person.
2. **Organizations, People and Contacts lists: offer filter.** *All offers* or one offer,
   remembered per browser or device.
   - One offer: the stage column shows that offer's stage, and contacts without that deal
     are hidden. This is the "my LearnWohl pipeline" view. The stage filter applies to that
     offer.
   - *All offers*: each row shows chips (*Consulting: suspect · LearnWohl: customer*). The
     stage filter means "has a deal at this stage".
3. **Quick creation** (manual business entry, card scan, document scan, sign capture, add
   person) asks for **offer + stage**, defaulting to the offer used last. LinkedIn import keeps
   creating people and employers as Consulting candidates.
4. **Logging a contact:** offer picker, filled in automatically when there is exactly one
   open deal, and "general" is allowed. The Contacts page counts ("contacted this month")
   follow the offer filter.
5. **Settings → Offers:** add, rename, set website, reorder, archive.
6. **Next steps** live on deals. Every place that lists next steps today lists deal next
   steps, with the offer name.

## Statistics

The Statistics page gets the same offer filter. Everything already on it is split by offer:

1. **Effort:** activities count toward their offer. General entries count only under *All
   offers*. Hours and € per hour are per offer.
2. **Pipeline:** deals per stage, stage changes and stuck deals, per offer. History continues
   without a gap because existing rows are marked Consulting.
3. **Money, one-off:** sales filtered by their deal's offer.
4. **Money, subscriptions (new):**
   - MRR now: the sum of running subscriptions.
   - Subscribers now: deals with a running subscription.
   - Per period: new MRR, lost MRR (subscriptions ended), and subscription revenue
     (€/month × the days each subscription ran inside the period ÷ the days in that month).
   - Total € won = one-off + subscription revenue, so "how much work for X euros" covers both
     kinds of revenue.

Subscription revenue is **calculated** from what was entered, not checked against payments.
The page labels it "calculated". If a customer stops paying and the subscription is not
ended, MRR is overstated. That is the gap the later billing sync closes.

## Privacy

1. **Privacy notice** (`/privacy`, linked from first outreach): the purpose becomes *direct
   marketing of my own consulting services and software products*. The product list is
   generated from the active offers, so a new offer updates the notice automatically. Only
   the list is generated; the legal wording around it is fixed.
2. **Opt-out stays on the contact.** `do_not_contact` blocks every offer. An objection to
   direct marketing (Art. 21(3) GDPR) ends all of it, so a per-offer opt-out would be wrong.
3. **Art. 30 record**, activity 1 (`docs/gdpr/art30-processing-record.md`): fill in the
   purpose and legal basis that are TODO today.
   - Purpose: B2B marketing and customer management for consulting and software products.
   - Legal basis: legitimate interest (Art. 6(1)(f)) for prospects, contract (Art. 6(1)(b))
     for paying subscribers.
   - New data category: subscription amounts and dates.
4. **Retention:** a running subscription blocks the inactivity deletion, both on the
   organization and on a person who owns a deal.
5. **Erasure and data export** include deals, subscriptions and offer-tagged log entries,
   cascading from the organization or person.

This is a reading of the GDPR, not legal advice. The notice wording should be reviewed
before any cold outreach for the apps. Unsolicited email to businesses is restricted
separately by UWG §7. That rule applies to consulting outreach today and is not changed
here.

## Agents and API

- The `Mission` gets an `offer_slug` (`consulting`). Research creates a Consulting deal at
  `candidate` with each new organization. Scout and outreach read and move that offer's deal
  instead of the organization's columns. No behaviour change.
- MCP tools (`manual_promote`, `manual_drop`, `contact_search`, …) act on the Consulting deal
  unless an offer is given.
- **API compatibility:** until the new mobile build is installed, the API still accepts and
  returns `pipeline_stage`/`status`/`next_step` on organizations and people, meaning that
  record's Consulting deal. The new deal endpoints are added alongside. The compatibility
  fields are removed in phase 5.

## Build order

Each phase goes live on its own and leaves the app working.

1. **Foundation, no visible change.** Migration and backfill; deal data layer; every read
   and write of a stage moved to deals (web, API with compatibility fields, MCP, agents,
   statistics, snapshots). Proof: deals per stage equal the old column counts, checked on
   production after deploy.
2. **Offers visible on the web, plus privacy.** Settings → Offers, Deals panel, list offer
   filters, offer + stage in quick creation, offer picker on log entries. Privacy notice,
   Art. 30 record, retention and erasure/export changes. Privacy ships here, before any app
   outreach depends on it.
3. **Money.** Subscriptions, sales attached to deals, statistics by offer with MRR.
4. **Mobile app:** the same screens against the API from phases 1–3.
5. **Cleanup:** once the updated mobile app is installed and production has been checked,
   drop the old stage columns, `sales.contact_id` and the API compatibility fields.

**Rollback:** until phase 5 the old columns still exist, so the code can be rolled back.
Stage changes made after the deploy would be missing from them, which is why phase 1 is
checked on production before phase 2 starts.

## Testing

- **Integration, on real Postgres** (`tests/integration/`, not mocks): the migration is safe
  to re-run; backfill counts match the old columns; duplicate live deals are rejected; a
  deal needs an owner; erasure cascades to deals and subscriptions; snapshot and
  stage-history triggers write `offer_id`; workspace isolation for offers and deals.
- **Unit:** offer auto-pick for log entries (zero, one, several open deals); subscription
  revenue for subscriptions starting or ending partway through a period, price changes, and
  months of different lengths; MRR.
- **End-to-end (web):** add a LearnWohl deal to an organization, move its stage, start a
  subscription, filter the list to LearnWohl, check statistics.
- **Mobile:** Jest tests for the Deals panel, offer filter and log-entry picker.
- Commits only go in when pytest's own exit code is 0.

## Later (not in this build)

- **Billing sync from the apps.** Subscriptions get `external_source` + `external_id`
  (unique together). A sync matches a paying customer to a deal by email address or domain;
  an unmatched customer goes to a review list instead of creating records. Synced
  subscriptions are read-only in the CRM. Manual entry stays for anything the sync does not
  cover.
- **Agents for app leads.** One `Mission` per offer (identity, targets, fit criteria,
  outreach style), selected by `offer_slug`. Research levels per offer (language schools for
  LearnWohl, galleries for LeGuild.art).

## Left out on purpose

- Offer-specific stage vocabularies.
- Per-offer opt-out (see Privacy, point 2).
- Several live deals for the same offer and contact.
- Deal values, win probabilities and forecasts.
- Invoicing. The CRM is not the accounting system.
