# Contracts: build plan

Design: `docs/plans/2026-11-27-contracts-design.md`. Five steps, one commit each, each step green
(ruff + unit + integration + e2e) before the next starts.

## Rules for every step

- **Test first.** Write the failing test, watch it fail for the right reason, then write the code.
- **Real Postgres for SQL.** Every new query runs in `tests/integration/` against a migrated database
  (`TEST_DATABASE_URL`; locally the Docker recipe in the `verify-new-sql-on-real-postgres` memory).
  Mocked route tests alone have shipped a wrong table name before.
- **Full CI locally before a commit:** `uv run ruff check .`, then `uv run pytest -q`,
  `uv run pytest tests/integration -q`, `uv run pytest tests/e2e -q`, gating on pytest's own exit code.
- **Workspace.** Every query filters by workspace; every handler uses the session workspace.
- **Invented names only** in tests, fixtures and commit messages (public repository).
- **i18n:** every new text gets an `en.json` and a `de.json` key (`tests/test_i18n.py` checks parity).

## Step 1: migration, `contract_id`, auto-create

**Files**
- `gcrm/db/migrations/111_contracts.sql` (new)
- `gcrm/contract_kinds.py` (new): `CONTRACT_KINDS = ("teaching_course", "workshop", "consulting", "other")`,
  `checked_kind(value) -> str` (unknown → `ValueError`).
- `gcrm/tools/deal_money.py`: `insert_sale_payments` gains `contract_id: int | None = None` and `title: str | None = None`;
  new `create_contract(cur, workspace_id, deal_id, title, kind="other") -> int`.
- `gcrm/backup_export.py`: see "Backup naming" below. Done in step 1 because the column name collides.

**Migration 111**
1. `contracts` (columns as in the design) with `UNIQUE (id, deal_id)`, index on `(workspace_id, deal_id)
   WHERE deleted_at IS NULL`.
2. `contract_links` with a `CHECK (url ~* '^https?://')` and length checks.
3. Row security for both, copied from migration 099: `ENABLE` + `FORCE ROW LEVEL SECURITY`, a policy
   `TO engcrm_workspace USING (workspace_id = request_workspace_id())`, `WITH CHECK` that also requires the
   parent (`deals` for contracts; `contracts` for links; `people` for `contact_person_id`) to be visible. Grants
   on the tables and their sequences.
4. `ALTER TABLE sales ADD COLUMN contract_id INTEGER`.
5. Backfill, as `CREATE OR REPLACE FUNCTION backfill_sale_contracts()` followed by `SELECT
   backfill_sale_contracts()`, touching only sales whose `contract_id IS NULL`:
   - one contract per `(deal_id, series_id)` and one per sale without a series;
   - title `COALESCE(NULLIF(trim(description), ''), offer.name || ' – ' || to_char(won_on, 'MM.YYYY'))`;
   - kind `other`; `deleted_at` = the sale's (for a series: set only when every payment is deleted);
   - `created_at` = the first payment's.
6. `ALTER TABLE sales ALTER COLUMN contract_id SET NOT NULL`, and a composite foreign key
   `(contract_id, deal_id) REFERENCES contracts (id, deal_id) ON DELETE CASCADE`: a payment can never
   belong to a contract on another deal.

**Insert path.** `insert_sale_payments` with no `contract_id` calls `create_contract` first (title: the
description, or "<offer> – MM.YYYY"; kind `other`) and gives every payment of the schedule that one id. With a
`contract_id`, it checks the contract is on the same deal and not deleted (the foreign key would catch the deal
mismatch too, as a database error rather than a clear message).

**Backup naming.** `sales.csv` today exports `series_id AS contract_id`. That becomes `series_id`, and the real
`contract_id` is added next to it. The README text inside the backup is updated. New `contracts.csv`
(id, deal_id, offer, owner, title, kind, assignment, contact_person_id, created_at) and `contract_links.csv`.

**Tests**
- `tests/integration/test_contracts_migration_db.py` (new). The backfill lives in a SQL function
  `backfill_sale_contracts()` that migration 111 creates and calls, so the test runs the same code. Inside one
  transaction that it rolls back at the end (Postgres DDL is transactional): `ALTER TABLE sales ALTER COLUMN
  contract_id DROP NOT NULL`, insert a series of 3, two single sales (one with a blank description) and a
  soft-deleted sale, all with `contract_id` NULL; call the function; assert one contract per series or single
  sale, the titles, the soft-deleted one's `deleted_at`, and no sale left without a contract; call it again and
  assert nothing changed. `test_migrations.py`'s existing "apply twice" test covers re-running the file.
- `tests/integration/test_contracts_db.py` (new): a sale without a contract gets one; a 4-payment schedule shares
  one; `contract_id` from another deal is refused; a contract from another workspace is invisible.
- `tests/integration/test_forecast_db.py`: one added test, the forecast totals for a seeded set are the same
  numbers the test asserted before the migration (the existing expected values must not change).
- `tests/integration/test_backup_export_db.py`: new files present, `sales.csv` has `series_id` and `contract_id`.
- `tests/integration/test_workspace_security.py`: already fails if a new table lacks row security. No change,
  it must stay green.

**Done when** all of the above pass and every existing integration test is still green.

## Step 2: Contracts list page

**Files**
- `gcrm/contract_math.py` (new, pure): `contract_summary(payments) -> dict` (value, hours, rate, collected,
  open, start, end, cancelled) and `timing(summary, today) -> "running" | "upcoming" | "finished"`.
- `gcrm/tools/db_contracts.py` (new): `list_contracts(workspace_id, offer, kind)`: contracts with owner name,
  offer, kind and their payments in one query (`LEFT JOIN sales`), grouped in Python with `contract_math`.
- `gcrm/api/routers/contracts.py` (new): `GET /contracts/` with `offer` (via `web_offer_filter`) and `kind`
  query parameters. Registered in `gcrm/api/main.py`.
- `gcrm/ui/templates/contracts.html` (new): totals line, three sections (Finished in a closed `<details>`).
- `gcrm/ui/templates/base.html`: `nav.contracts` tab.

**Tests**
- `tests/test_contract_math.py` (new, unit): ends today → running; starts tomorrow → upcoming; no work
  dates → due days → won days; all cancelled → finished and zero in totals; collected + open = value; hours
  None when no payment has hours.
- `tests/integration/test_contracts_web_db.py` (new): the page renders all three sections from real rows; kind
  and offer filters; another workspace's contracts are not listed.
- `tests/e2e/test_every_page_renders.py` and `tests/test_nav.py`: add `/contracts/`.

## Step 3: Contract page

**Files**
- `gcrm/tools/db_contracts.py`: `get_contract(id, workspace_id)`, `update_contract(...)`,
  `delete_contract(...)` (soft-deletes the contract and its payments in one transaction),
  `add_link`, `remove_link`, `move_link`, `add_payment(contract_id, amount, due, status)`.
  Each write logs its audit event (`contract.added`, `.edited`, `.deleted`, `.link_added`, `.link_removed`).
- `gcrm/api/routers/contracts.py`: `GET /contracts/{id}`; `POST /contracts/{id}` (edit),
  `/contracts/{id}/delete`, `/contracts/{id}/links`, `/contracts/{id}/links/{link}/delete`,
  `/contracts/{id}/links/{link}/move`, `/contracts/{id}/payments`. Writes need `require_admin`.
  The existing sale controls keep posting to `/deals/{deal_id}/sales/...` with `next=/contracts/{id}`.
- `gcrm/ui/templates/contract_detail.html` (new): header, money strip, assignment
  (`white-space: pre-wrap`), links (`target="_blank" rel="noopener noreferrer"`), payments in a closed
  `<details>` reusing `sale_item` from `partials/sale_rows.html`.

**Tests**
- Unit: `javascript:alert(1)`, `data:text/html,…`, `ftp://x`, blank label, 2,001-character URL refused;
  `https://example.org/a` accepted. Unknown kind refused. Assignment over 20,000 characters refused.
- Integration: edit saves; delete hides the contract and its payments from the list *and* the forecast;
  another workspace's contract is 404 on GET and on every POST; POST without CSRF refused; links keep their order
  after a move; assignment containing `<script>` renders escaped.

## Step 4: New contract, and contracts on deal cards

**Files**
- `gcrm/ui/templates/partials/sale_rows.html` (or a new `partials/contract_form.html`): the form gains
  **title** (required) and **kind**.
- `gcrm/api/routers/deals.py` `deal_sale_add` and `gcrm/api/routers/statistics.py` `/organizations/{id}/sales`:
  accept `title` and `kind`, create the contract, then its payments, in one transaction. Button text
  `sales.record` → `contracts.new`.
- `gcrm/tools/deal_money.py` `deal_money`: also returns each deal's contracts (id, title, kind, summary).
- `gcrm/ui/templates/organization_detail.html` (Sales card) and `partials/deals_panel.html` (person deals):
  list contracts by title, linking to `/contracts/{id}`, with value and timing. Loose payment rows move to the
  contract page.
- `GET /contracts/new` + `POST /contracts/` on the Contracts page: pick the organization or person and the
  offer (deal), then the same form.
- `gcrm/api/routers/api_deals.py` (phone): unchanged; it gets an auto-created contract.

**Tests**
- `tests/test_deals_routes.py`: the form passes title and kind through; missing title → 400.
- Integration: a new contract from the organization page shows up on `/contracts/` and on the organization page;
  a monthly contract makes one contract with N payments; the phone endpoint still creates a sale (and a contract).
- `tests/e2e`: one flow: create a contract on an organization, open it from the Contracts page, add a link.

## Step 5: Backup README, help, German texts

- Help entry "Contracts" / "Verträge" (via the existing help articles mechanism; check how other entries are
  seeded before choosing a migration or the editor).
- Read every new German text once in context on the rendered pages.
- `README.md` / `RUNBOOK.md`: one line each where pages are listed, if they list pages.

## After the last push

1. CI green, deploy done.
2. With Chris's OK, a read-only production check: `SELECT count(*) FROM sales WHERE contract_id IS NULL`
   (expect 0; NOT NULL makes it impossible, this confirms the migration ran) and the contract count against
   the number of existing sale series + single sales.
3. Open `/contracts/` live.
4. Chris sets the kind and writes the assignment for each migrated contract.
