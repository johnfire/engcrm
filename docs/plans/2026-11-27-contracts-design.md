# Contracts: the business deals made, and what each one asks of us

Date: 2026-11-27 · Status: designed, not built

## Why

The CRM knows what each deal is worth: sales carry the amount, hours (migration 095), the work
window (096), a status, and a payment schedule (a contract paid monthly is N sale rows sharing a
`series_id`, 086). It does not know **what we agreed to do**. Each customer asks for something
different: a year-long AI course at one school, a course on business applications of AI for
Kaufleute at another, a consulting project building systems for a company. That information has no
home, there is no list of all deals made across customers, and there is nowhere to point at the
materials that go with a deal.

A contract has no row of its own today: `series_id` is only a UUID shared by payment rows. A
**Contracts** screen needs one.

This is not accounting. Billing stays in the billing records; the screen shows the whole contract's
value and hours, not a ledger.

## Decisions (agreed with Christopher, 2026-11-27)

| Question | Decision |
|---|---|
| How a contract relates to sales | A new `contracts` row **wraps** the existing sales: its payments are the sale rows. Value, hours, €/h, collected and the work dates are **computed from the payments**, never stored twice, so the Contracts page and the Forecast always agree. |
| What a contract belongs to | A deal, so a company (organization) or a person, and an offer. Euros only. |
| How the assignment is recorded | A **kind** (teaching course, workshop, consulting, other), a title, and one free-text **assignment** field, plus an optional contact person. No per-kind form fields. |
| Attachments | **Links** now (label + URL). PDF upload is a separate, later project if links turn out not to be enough. |
| List layout | Grouped by timing: **Running now**, **Upcoming**, **Finished**. |
| Existing sales | **Every sale belongs to a contract.** A one-off sale is a contract with one payment. The migration creates the contracts for existing sales. |
| Monthly payments | Secondary: collapsed on the contract page. The whole-contract totals come first. |
| Phone | Web only in v1. |

## Data model

### `contracts`

| Column | Notes |
|---|---|
| `id`, `workspace_id`, `deal_id` | `deal_id` references `deals(id)` ON DELETE CASCADE. Workspace-scoped like everything else. |
| `title` | Required, up to 200 characters. |
| `kind` | `teaching_course`, `workshop`, `consulting`, `other`. Checked in the application layer, like stages (see migration 041 for why). |
| `assignment` | Free text, up to 20,000 characters. Shown as plain text with line breaks kept (`white-space: pre-wrap`, autoescaped). No Markdown: there is no renderer in the app, and adding one needs an HTML sanitizer, a stored-XSS route. Can be added later. |
| `contact_person_id` | Optional, `people(id)` ON DELETE SET NULL. The customer's person for this contract, e.g. the course coordinator. |
| `created_at`, `updated_at`, `deleted_at` | Soft delete. |

### `contract_links`

| Column | Notes |
|---|---|
| `id`, `workspace_id`, `contract_id` | `contract_id` ON DELETE CASCADE. |
| `label` | Required, up to 200 characters. |
| `url` | Required, up to 2,000 characters, must start with `http://` or `https://`. Rendered with `target="_blank" rel="noopener noreferrer"`. |
| `sort_order`, `created_at` | |

### `sales`

- Add `contract_id INTEGER NOT NULL REFERENCES contracts(id) ON DELETE CASCADE` (NOT NULL after the
  backfill).
- Nothing else changes. `series_id`, `series_part` and `series_total` stay: the forecast, statistics
  and contract-flow charts read them. Once nothing reads them, `contract_id` makes them redundant and
  they can go in a later cleanup.

### Computed per contract (from its payments, cancelled ones left out)

- **Value** = sum of `amount_eur`; **hours** = sum of `hours` (None when none recorded); **€/h** =
  value / hours; **collected** = sum of collected payments; **open** = value − collected.
- **Start** = earliest `work_from`; else the earliest due day (`expected_on`); else the earliest
  `won_on`.
- **End** = latest `work_to`; else the latest due day; else the latest `won_on`.
- **Cancelled** = every payment is cancelled.

### Migration (backfill)

1. Each existing payment series (`series_id`) becomes one contract; each sale without a series
   becomes a one-payment contract. Soft-deleted sales get a soft-deleted contract.
2. Title: the sale's description; when blank, "<offer name> – <month of won_on>". Kind: `other`.
3. Every sale's `contract_id` is set, then the column becomes NOT NULL.

Every step fills only what is not filled yet, so running the migration twice changes nothing.

## Screens

### Contracts list (`/contracts/`)

A top-level menu tab, **Contracts** / *Verträge* (the menu sorts alphabetically).

| Section | Rule | Sorted by | Shown |
|---|---|---|---|
| Running now | start ≤ today ≤ end | soonest end first | open |
| Upcoming | start > today | soonest start first | open |
| Finished | end < today, or cancelled | most recent end first | collapsed |

- Row: company · title · kind · dates · value · hours · €/h · collected. A finished contract with
  money still open shows "X € still open". A cancelled one carries a *cancelled* tag and is left out of
  all totals.
- Each section heading carries its count, value and hours; a line at the top totals the page:
  value, hours, average €/h, collected.
- Filters: **kind**, and the existing **offer** filter (remembered per browser).
- A **New contract** button (pick company or person, offer, then the contract form).
- Not in v1: search, export, phone screen.

### Contract page (`/contracts/{id}`)

- **Header:** title · kind · company (links to the organization) · offer · dates · contact person
  (links to the person). **Edit** turns title, kind, contact person and assignment into a form.
- **Money strip:** value · hours · €/h · collected · open.
- **Assignment:** plain text, line breaks kept.
- **Links:** label → URL, opened in a new tab. Add, remove, move up or down.
- **Payments**, collapsed by default: the existing payment rows and controls (`sale_rows.html`),
  reused, not copied: mark received, change due day, whole-contract status, hours and work dates.
  **+ Add payment** adds one payment (amount, due day, status) to this contract.
- **Delete contract:** confirm step, then soft-deletes the contract and its payments together.

### Deal cards (organization and person pages)

**Record sale** becomes **New contract**: today's sale form plus **title** (required) and **kind**.
Contract and payments are created in one transaction. The deal card lists its contracts by title,
linking to the contract page, instead of loose payment rows.

## What else changes

- **`insert_sale_payments`** (`gcrm/tools/deal_money.py`) is the one place sales are created (web form,
  phone API, statistics path). It takes an optional contract; without one it creates the contract itself
  (title from the description or "<offer> – <month>", kind `other`). Together with NOT NULL, no payment can
  exist without a contract.
- **Backup export:** `contracts.csv` and `contract_links.csv`; the backup README describes them. `sales.csv`
  already has a column called `contract_id` that holds the `series_id`; it is renamed `series_id`, and the real
  `contract_id` is added.
- **Integrity:** a composite foreign key `(contract_id, deal_id) → contracts (id, deal_id)` means a payment
  can never sit on a contract of another deal. Both new tables get workspace row security like every other
  table.
- **Audit log:** `contract.added`, `contract.edited`, `contract.deleted`, `contract.link_added`,
  `contract.link_removed`.
- **i18n:** English and German for every text.
- **Help:** a short "Contracts" entry.

Unchanged: Forecast, Statistics, contract-flow charts and the income plan read sales, and sales keep
their amounts, dates and statuses. The phone syncs deal totals only (migration 109's trigger keys on
`deal_id`), so it is untouched.

## Testing

- **Grouping:** ending today is Running; starting tomorrow is Upcoming; no work dates falls back to due
  days, then won days; all payments cancelled is Finished and out of every total.
- **Money:** cancelled payments are left out; collected + open = value.
- **Links:** `http`/`https` accepted; `javascript:`, `data:`, `ftp:`, blank label refused.
- **Insert path:** a sale without a contract gets one; a monthly schedule shares one contract.
- **Pages (TestClient):** list and contract page render; another workspace's contract is 404; POST
  without CSRF is refused; edit and delete work; deal cards list contracts.
- **Migration on real Postgres:** seed a series, single sales and a soft-deleted sale; run twice; one
  contract per series or single sale, no sale without a contract, second run changes nothing.
- **Forecast unchanged:** forecast totals on the same seed data are identical before and after the
  migration.

## Build order

One commit each:

1. Migration, `contract_id`, auto-create in `insert_sale_payments`.
2. Contracts list page and menu tab.
3. Contract page: assignment, links, edit, delete, payments.
4. "New contract" on deal cards; deal cards list contracts.
5. Backup export, help entry, German texts.

After deploy: a read-only production check (no sale without a contract; the contract count matches the
existing sales), then the kinds and assignments of the migrated contracts are filled in by hand.

## Later

- PDF upload (storage on the server volume, size cap, PDF check, part of the backup).
- Markdown in the assignment, with a sanitizer.
- Contracts on the phone.
- Dropping `series_id` / `series_part` / `series_total` once everything reads `contract_id`.
