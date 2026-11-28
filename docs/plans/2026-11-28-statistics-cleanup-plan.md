# Statistics page clean-up — build plan (2026-11-28)

The Statistics page (`/statistics`) shows figures that are wrong for how the CRM is used now, or that nobody
needs. This plan says what changes. Design background: `docs/plans/2026-10-05-statistics-design.md`.

## What we found on live data (read-only, 2026-11-28)

- No sale is `collected` yet, so "Won" (collected only) is €0. Almost all the money is `booked`,
  `contracted` or `expected`, and the largest share is `expected`.
- Every sale belongs to a contract (`sales.contract_id`, NOT NULL). A monthly contract is stored as one
  sale row **per month** (`series_part` / `series_total`). Counting rows counts payments, not sales.
- The `subscriptions` table is empty, so MRR is always 0. Monthly contracts are sales, not subscriptions.
- "Sales pipeline" (booked + contracted) ignores the chosen period. It is an all-time open total.
- Stuck list: brand-new organizations show as "never contacted" (the clock starts at nothing). An
  organization whose only activity is an **inbound** message counts as never contacted. Deals held by
  a person (no organization) are never checked, although there are many of them in working stages.
- Pipeline-over-time lines: each one is stretched between its own min and max, and weeks with no
  snapshot row for a stage are skipped, so lines start partway across.

## Decisions (Chris, 2026-11-28)

- **Sold** = sales with status `booked`, `contracted` or `collected`, by the day the sale was agreed
  (`won_on`). **Expected** stays its own status. It is an estimate (agreed in principle, not in
  writing), more than a hope, and the page shows it as a full figure, not small print.
- **Collected** = money in (`collected_on` in the period).
- Hours are not tracked yet. Remove hours and € per hour from the page. **Leave the Effort table and
  the default-minutes form exactly as they are.** Chris is still deciding about them.
- MRR tiles are **hidden while the workspace has no subscription**, and they come back on their own.
- Pipeline over time becomes **one zero-based stacked bar chart of the working stages**.
- Keep: the period buttons and date range, Activities, New organizations, New people, Pipeline now,
  Stage changes, New contacts by source, and the over-time charts for activities, new organizations,
  new people and money.

## Changes

### 1. Money figures (`gcrm/tools/statistics.py`, `_summary`)
- Add `sold_eur` and `sold_contracts`: status in `booked`, `contracted` or `collected`, `won_on` in
  [start, end]. `sold_contracts` counts **distinct `contract_id`**.
- Add `expected_eur` and `expected_contracts`: same rule, status `expected`.
- `collected_eur`: collected sales with `collected_on` in the period (today's `one_off_eur`).
- Drop `won_eur`, `eur_per_hour` and `sales` (the row count) from the summary. Keep
  `subscription_eur` and the MRR moves for the MRR tiles.
- Previous-period deltas for sold, expected, collected and contracts, like the other tiles.
- Put the status groups in `gcrm/sale_status.py` (one place). Add `SOLD_STATUSES = ("booked",
  "contracted", "collected")` and reuse the existing tuples.
- The "Open now" figure stays all-time, but its label says so: "Open now (all time)", split into
  firm (booked + contracted) and expected.

### 2. Tiles (`gcrm/ui/templates/statistics.html`)
Keep the order: Activities · Sold € · Contracts sold · Expected € · Collected € · Open now (all
time) · [MRR now · MRR moves · Subscription revenue, only when the workspace has a subscription] ·
Moved forward · New organizations · New people.
- Remove the Hours, Won and € per hour tiles.
- Rename "Promotions" to **"Moved forward"** / DE **"Weitergekommen"**, with a title tooltip:
  "Deals that moved up a pipeline stage in this period".
- Add `has_subscriptions` to `get_statistics()` (any non-deleted subscription in the workspace,
  whatever the offer filter) and use it to show or hide the three MRR tiles.

### 3. Sales table ("Sales and the work behind them")
- One row **per contract** with `won_on` in the period and status `expected`, `booked`, `contracted`
  or `collected` (not `cancelled`). Columns: organization or person (linked), offer, contract title,
  status, total € (sum of its sale rows), agreed on (`won_on`), payments (`series_total` or 1),
  weeks from first contact, activities before the sale.
- Drop the Hours and € per hour columns. Update the hint text: the table no longer means "collected only".
- Keep the weeks and activities logic, but base it on the contract's `won_on`, and on the previous
  contract's `won_on` for the "since the last sale" window.

### 4. Remove hours elsewhere
- Remove the "Hours per week" section, plus the `weeks` query in `get_statistics()` if nothing else uses it.
- Remove the hours chart from Over time (`_trend_charts` in `gcrm/api/routers/statistics.py`, and
  the hours series in `gcrm/tools/statistics_history.py` if nothing else reads it).
- Do **not** touch the Effort table, `activity_minute_defaults`, or the `/statistics/minutes` form.

### 5. Money over time
- Replace the "won" chart with **"Sold"** (booked + contracted + collected by `won_on`) per bucket.
  Today it is empty because it reads `collected_on` only.
- Leave subscription revenue in the series. It is 0 while there are no subscriptions.

### 6. Stuck list (`get_statistics`, the `stuck` query)
- A deal is stuck when it is in a working stage (`suspect`, `nibble`, `prospect`, `opportunity`)
  and the **latest** of these is more than 28 days ago:
  - its last activity, **counting inbound messages** (but still not next-step/plan entries);
  - the day the deal was created;
  - the day it entered its current stage (latest `stage_changes` row for that deal).
- Include **person-held deals**. Their activities are that person's `people_interactions`. Link
  them to `/people/{id}`. Organization deals keep today's rule: the organization's log plus its
  people's logs.
- Show "last activity on …" or "added on …, no activity yet", whichever applies. Keep the limit of
  25, and show the total count in the heading when there are more.

### 7. Pipeline over time
- New `stacked_bars(buckets, series, title, …)` in `gcrm/charts.py`. One bar per bucket, one
  segment per stage, a **shared zero-based** scale, a y-axis with a few ticks, a legend, a `<title>`
  tooltip per segment ("Woche 16.11.: prospect 3"), and a `<details>` table under it like the other
  charts. Colours come from CSS custom properties, one per stage, in both light and dark themes.
- Stages: `suspect`, `nibble`, `prospect`, `opportunity`, `customer`. Count organization and
  person deals together.
- **A bucket with no snapshot row for a stage is 0**, not skipped. Buckets before `logged_since`
  stay empty, and the chart says the log starts on that date (as today).
- Under the chart, show **Candidates**, **Not now** and **Dropped (not in pipeline)** as plain
  numbers: the latest value and the change since the first bucket shown.
- Remove the small-multiples block and the `spark()` calls on this page. Delete `spark()` only if
  nothing else uses it.

### 8. Meaning of "expected"
- `gcrm/sale_status.py` docstring: `expected` = "estimated: a conservative forecast built on solid
  facts (a verbal agreement, the going market rate), not yet in writing".
- Wherever the UI explains sale statuses (search the i18n files and the sale form for the
  explanation), use the same wording in EN and DE. The label stays "Expected" / "Erwartet".

## How to build it
- Follow the `coding-standards` skill. Write tests first. The repo is **public**, so test data
  uses invented organizations and people only.
- Update the tests that asserted removed features (hours tile, € per hour, won). List every test
  you changed or removed and why in the commit message and your report. **Never delete or weaken a
  test just to make a run pass.** If a test fails for a reason you don't understand, stop and report it.
- New SQL must run against real PostgreSQL. Mocked tests have missed broken SQL before. Integration
  tests **skip** unless `TEST_DATABASE_URL` is set (`tests/conftest.py`), so a run without it proves
  nothing. Start a throwaway database:
  `docker run -d --rm --name engcrm-verify -e POSTGRES_PASSWORD=x -e POSTGRES_DB=verify -p 55432:5432 pgvector/pgvector:pg16`,
  wait until `docker logs engcrm-verify` shows "PostgreSQL init process complete", then
  `docker exec engcrm-verify psql -U postgres -d verify -c "CREATE ROLE artcrm_admindude SUPERUSER LOGIN"`,
  and run with `TEST_DATABASE_URL=postgresql://postgres:x@localhost:55432/verify`. Check that the
  statistics integration tests actually **ran** (not skipped). Stop the container afterwards.
- Before committing, run the CI steps in order and check each exit code: `uv run ruff check .`,
  `uv run pytest tests -q -m "not integration and not e2e and not network"`,
  `uv run pytest tests/integration -q`, `uv run pytest tests/e2e -q`.
- Render `/statistics` through the test client with fixture data, and check that the page shows the
  new tiles, no hours anywhere, the stacked chart, and a person deal in the stuck list.
- Commit to `main` (no branch). **Do not push.**

## Done when
- Every point above is in, and all four CI steps pass locally.
- With fixture data like the live shape (monthly contracts in several statuses, no collected sales,
  no subscriptions), the page shows non-zero Sold and Expected, contracts counted once each, no MRR
  tiles, no hours, and the stacked chart starting at zero.
